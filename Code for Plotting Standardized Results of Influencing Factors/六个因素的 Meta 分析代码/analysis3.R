# Health workforce shortage and cancer-specific mortality/survival: HR meta-analysis.
# Open this script in RStudio and click Source. Outputs are genuine vector SVGs.
# Plot style follows Delayed diagnosis/HR_Meta_Analysis_Cancer_Specific_2026-10-17.
# One independent estimate per study; published HRs and confidence limits remain in the input file.

if (.Platform$OS.type == 'windows') Sys.setlocale('LC_CTYPE','English_United States.utf8')
script_files <- unlist(lapply(sys.frames(),function(x) x$ofile))
if(length(script_files)) {
  analysis_dir <- dirname(normalizePath(tail(script_files,1),winslash='/'))
} else {
  script_arg <- grep('^--file=',commandArgs(),value=TRUE)
  analysis_dir <- if(length(script_arg)) dirname(normalizePath(sub('^--file=','',script_arg[1]),winslash='/')) else getwd()
}
setwd(analysis_dir)
library(meta)
library(metafor)
library(grid)
dir.create('previews',showWarnings=FALSE)

d <- read.csv('included_HR_cancer_specific.csv',fileEncoding='UTF-8-BOM',check.names=FALSE)
stopifnot(nrow(d)==7L,!anyDuplicated(d$cohort),
  all(d$raw_lower>0 & d$raw_lower<=d$raw_HR & d$raw_HR<=d$raw_upper))
d$HR <- ifelse(d$invert,1/d$raw_HR,d$raw_HR)
d$lower <- ifelse(d$invert,1/d$raw_upper,d$raw_lower)
d$upper <- ifelse(d$invert,1/d$raw_lower,d$raw_upper)
d$analysis_origin <- ifelse(d$invert,'Reciprocal direction harmonisation*','Published direction')
d$study <- paste(d$author,d$year)
d$study_label <- paste0(d$study,ifelse(d$invert,'*',''))
d$logHR <- log(d$HR)
d$SE <- (log(d$upper)-log(d$lower))/(2*qnorm(.975))
d$point_label <- paste0(d$study_label,'\nHR = ',formatC(d$HR,format='f',digits=3))
stopifnot(all(d$lower<=d$HR & d$HR<=d$upper),all(is.finite(d$SE)),all(d$SE>0))

fit_meta <- function(z,ci='classic') metagen(TE=logHR,seTE=SE,studlab=study_label,data=z,sm='HR',
  common=TRUE,random=TRUE,method.tau='REML',method.random.ci=ci,
  adhoc.hakn.ci=if(ci=='HK') 'se' else '',prediction=nrow(z)>=3,method.predict='HTS',
  control=list(stepadj=.25,maxiter=10000))
m <- fit_meta(d)
m_hk <- fit_meta(d,'HK')
rma_check <- rma(yi=d$logHR,sei=d$SE,method='REML',test='z',control=list(stepadj=.25,maxiter=10000))
stopifnot(abs(as.numeric(rma_check$b)-m$TE.random)<1e-5,abs(rma_check$tau2-m$tau2)<1e-5)

loo_raw <- as.data.frame(leave1out(rma_check,transf=exp))
loo <- data.frame(omitted_id=d$study_id,omitted_study=d$study,
  HR=loo_raw$estimate,lower=loo_raw$ci.lb,upper=loo_raw$ci.ub,
  p=loo_raw$pval,tau2=loo_raw$tau2,
  I2_percent=100*pmax(0,(loo_raw$Q-(nrow(d)-2))/loo_raw$Q))

# Small-study tests are retained to match the reference analysis, but k=7 is below the usual k>=10 threshold.
egger_fit <- lm(I(logHR/SE) ~ I(1/SE),data=d)
eg <- coef(summary(egger_fit))[1,]
eg_ci <- confint(egger_fit)[1,]
eg_check <- regtest(d$logHR,sei=d$SE,model='lm',predictor='sei')
stopifnot(isTRUE(all.equal(unname(eg[4]),eg_check$pval,tolerance=1e-8)))
begg <- ranktest(d$logHR,vi=d$SE^2)
pf <- function(x) ifelse(is.na(x),'NA',ifelse(x<.001,'< 0.001',paste0('= ',formatC(x,format='f',digits=3))))

# Estimand sensitivity: Cox cause-specific HR and Fine-Gray subdistribution HR are not identical estimands.
d_cox <- d[d$estimator_group=='Cox',]
d_fg <- d[d$estimator_group=='Fine-Gray',]
m_cox <- fit_meta(d_cox)
m_fg <- fit_meta(d_fg)
d$fg_indicator <- as.integer(d$estimator_group=='Fine-Gray')
estimand_meta_regression <- rma(yi=logHR,sei=SE,mods=~fg_indicator,data=d,method='REML',test='z')

# Model-selection sensitivity for Fleming: pre-stage model estimates a broader total association.
d_fleming_pre <- d
ix_f <- match('Fleming_2018',d_fleming_pre$study_id)
d_fleming_pre$HR[ix_f] <- 1.18
d_fleming_pre$lower[ix_f] <- 1.06
d_fleming_pre$upper[ix_f] <- 1.30
d_fleming_pre$logHR <- log(d_fleming_pre$HR)
d_fleming_pre$SE <- (log(d_fleming_pre$upper)-log(d_fleming_pre$lower))/(2*qnorm(.975))
m_fleming_pre <- fit_meta(d_fleming_pre)

target_cancers <- c('breast cancer','leukemia','prostate cancer','lung cancer','pancreatic cancer','ovarian cancer')
target_titles <- c('Breast Cancer','Leukemia','Prostate Cancer','Lung Cancer','Pancreatic Cancer','Ovarian Cancer')
subgroup_counts <- vapply(target_cancers,function(x) sum(d$cancer==x),integer(1))

draw_forest <- function() {
  mp <- m
  mp$lower <- log(d$lower); mp$upper <- log(d$upper)
  forest(mp,leftcols=c('studlab','TE','seTE'),leftlabs=c('Study','logHR','SE(logHR)'),
    rightcols=c('effect','ci','w.common','w.random'),
    rightlabs=c('HR','95% CI','Weight\n(fixed)','Weight\n(random)'),
    text.common='Fixed effect',text.random='Random effects (REML)',
    text.predict='95% prediction interval',
    xlab='Hazard ratio (lower vs higher workforce availability)',
    smlab='Cancer-specific mortality / survival',
    col.square='grey65',col.square.lines='grey30',col.diamond.common='black',
    col.diamond.random='firebrick3',col.predict='royalblue3',
    print.I2=TRUE,print.tau2=TRUE,print.Q=TRUE,print.pval.Q=TRUE,
    test.overall.common=TRUE,test.overall.random=TRUE,prediction=TRUE,
    fontsize=10,digits=3,digits.se=4,digits.tau2=4,
    label.left='Lower cancer-specific mortality hazard',
    label.right='Higher cancer-specific mortality hazard',
    addrows.below.overall=6,xlim=c(.25,3),at=c(.25,.5,1,2))
  grid.text('* Published higher-vs-lower estimate inverted as 1/HR; original values retained in the input table.',
    x=unit(.5,'npc'),y=unit(.022,'npc'),gp=gpar(fontsize=8.5,col='grey30'))
}

side_labels <- function(x,y,labels,left,xleft,xright,ylo,yhi,cex=.78) {
  for(side in c(TRUE,FALSE)) {
    ix <- which(left==side)
    if(!length(ix)) next
    ix <- ix[order(y[ix])]
    yy <- seq(ylo,yhi,length.out=length(ix)); xx <- if(side) xleft else xright
    segments(x[ix],y[ix],xx,yy,col='grey75',lwd=.7)
    ww <- strwidth(labels[ix],cex=cex); hh <- strheight(labels[ix],cex=cex)
    pad <- .004*diff(par('usr')[1:2])
    rect(if(side) xx-ww-pad else xx-pad,yy-hh*.57,
      if(side) xx+pad else xx+ww+pad,yy+hh*.57,col='white',border=NA)
    text(xx,yy,labels[ix],adj=if(side) c(1,.5) else c(0,.5),cex=cex)
  }
}

draw_funnel <- function() {
  par(mar=c(5.5,5,5,2))
  ymax <- max(d$SE)*1.28; center <- m$TE.common
  core <- range(c(d$logHR,center+c(-1,1)*qnorm(.975)*ymax)); span <- diff(core)
  lim <- core+c(-.67,.67)*span
  plot(NA,xlim=lim,ylim=c(ymax,0),xlab='Hazard ratio (logarithmic scale)',
    ylab='Standard error of log(HR)',xaxt='n',
    main='Funnel plot: workforce availability and cancer-specific mortality')
  ticks <- c(.1,.25,.5,1,2,4,10); ticks <- ticks[log(ticks)>lim[1] & log(ticks)<lim[2]]
  axis(1,at=log(ticks),labels=ticks)
  polygon(c(center,center-qnorm(.975)*ymax,center+qnorm(.975)*ymax),
    c(0,ymax,ymax),col='grey94',border=NA)
  abline(v=center,lty=2,col='firebrick3')
  lines(center-qnorm(.975)*c(0,ymax),c(0,ymax),lty=3)
  lines(center+qnorm(.975)*c(0,ymax),c(0,ymax),lty=3)
  side_labels(d$logHR,d$SE,d$point_label,d$logHR<center,
    core[1]-.05*span,core[2]+.05*span,.06*ymax,.78*ymax)
  points(d$logHR,d$SE,pch=21,bg='grey65',cex=1.4)
  mtext(paste0('Egger intercept test: P ',pf(eg[4]),' (k = 7; df = 5)'),side=3,line=.5)
  mtext('Exploratory only because fewer than 10 studies are available',side=1,line=3.7,cex=.85)
  legend('bottomleft',legend=c('Fixed-effect centre','Pseudo 95% confidence limits'),
    lty=c(2,3),col=c('firebrick3','black'),bty='n',cex=.85)
}

draw_egger <- function() {
  par(mar=c(5.5,5,5,2))
  prec <- 1/d$SE; snd <- d$logHR/d$SE
  xr <- range(prec); span <- diff(xr); lim <- c(-.38*span,max(prec)+.48*span)
  yr <- range(c(0,snd,eg[1])); yr <- yr+c(-.22,.25)*max(diff(yr),1)
  plot(NA,xlim=lim,ylim=yr,xaxt='n',xlab='Precision: 1 / SE(log HR)',
    ylab='Standard normal deviate: log HR / SE',
    main='Egger regression: workforce availability and cancer-specific mortality')
  ticks <- pretty(c(0,max(prec))); ticks <- ticks[ticks>=0 & ticks<=max(prec)*1.1]
  axis(1,at=ticks,labels=ticks)
  segments(0,coef(egger_fit)[1],max(prec)*1.04,
    coef(egger_fit)[1]+coef(egger_fit)[2]*max(prec)*1.04,col='firebrick3',lwd=2)
  abline(h=0,lty=3,col='grey60')
  side_labels(prec,snd,d$point_label,prec<=median(prec),
    -.03*span,max(prec)+.03*span,yr[1]+.12*diff(yr),yr[2]-.1*diff(yr))
  points(prec,snd,pch=21,bg='grey65',cex=1.4)
  mtext(sprintf('Intercept = %.3f; t = %.3f; df = 5; P %s',eg[1],eg[3],pf(eg[4])),side=3,line=.5)
  mtext('Exploratory only because k = 7',side=1,line=3.7,cex=.85)
}

draw_leave_one_out <- function() {
  n <- nrow(loo); top <- n+4
  par(mar=c(3,1.5,2,1.5),family='sans')
  plot.new(); plot.window(xlim=c(0,1),ylim=c(-1.3,top))
  title('Leave-one-out sensitivity analysis',line=.1,cex.main=1.25)
  text(.5,top-.55,'Random-effects REML | Cancer-specific mortality / survival',cex=.84,col='grey35')
  text(.025,top-1.3,'Omitted study',adj=0,font=2,cex=.86)
  text(.56,top-1.3,'Pooled hazard ratio',font=2,cex=.86)
  text(.805,top-1.3,'HR [95% CI]',font=2,cex=.86)
  text(.955,top-1.3,'I2',font=2,cex=.86)
  segments(.02,top-1.65,.985,top-1.65,col='grey45')
  plot_min <- min(c(loo$lower,exp(m$lower.random)))
  plot_max <- max(c(loo$upper,exp(m$upper.random)))
  lo <- max(.15,floor(plot_min*10)/10); hi <- ceiling(plot_max*10)/10
  xx <- function(hr) .43+(log(hr)-log(lo))/(log(hi)-log(lo))*.27
  yy <- seq(top-2.4,2.6,length.out=n)
  for(i in seq_len(n)) {
    y <- yy[i]
    if(i%%2==0) rect(.02,y-.32,.985,y+.32,col='grey96',border=NA)
    segments(xx(1),y-.32,xx(1),y+.32,col='grey70',lty=2)
    text(.025,y,paste0('Omit ',loo$omitted_study[i]),adj=0,cex=.80)
    segments(xx(loo$lower[i]),y,xx(loo$upper[i]),y,lwd=1.35,col='grey25')
    segments(xx(loo$lower[i]),y-.09,xx(loo$lower[i]),y+.09,col='grey25')
    segments(xx(loo$upper[i]),y-.09,xx(loo$upper[i]),y+.09,col='grey25')
    points(xx(loo$HR[i]),y,pch=22,bg='grey65',col='grey30',cex=1.3)
    text(.805,y,sprintf('%.3f [%.3f, %.3f]',loo$HR[i],loo$lower[i],loo$upper[i]),cex=.77)
    text(.955,y,sprintf('%.1f%%',loo$I2_percent[i]),cex=.77)
  }
  segments(.02,1.75,.985,1.75,col='grey45')
  text(.025,1.15,'All 7 studies',adj=0,font=2,cex=.85)
  xmid <- xx(exp(m$TE.random)); xlow <- xx(exp(m$lower.random)); xhigh <- xx(exp(m$upper.random))
  polygon(c(xlow,xmid,xhigh,xmid),c(1.15,1.33,1.15,.97),col='firebrick3',border='firebrick3')
  text(.805,1.15,sprintf('%.3f [%.3f, %.3f]',exp(m$TE.random),exp(m$lower.random),exp(m$upper.random)),cex=.77,font=2)
  text(.955,1.15,sprintf('%.1f%%',100*m$I2),cex=.77,font=2)
  segments(xx(lo),.25,xx(hi),.25,col='grey30')
  ticks <- exp(pretty(log(c(lo,hi)),5)); ticks <- ticks[ticks>=lo & ticks<=hi]
  for(v in ticks) {segments(xx(v),.25,xx(v),.13,col='grey30');text(xx(v),-.12,formatC(v,digits=2,format='f'),cex=.76)}
  text(.56,-.72,'Hazard ratio (lower vs higher workforce availability)',cex=.82)
}

for(nm in c('forest','funnel','egger','leave_one_out')) {
  fun <- get(paste0('draw_',nm))
  wh <- switch(nm,forest=c(13,8.2),funnel=c(12,8),egger=c(12,8),leave_one_out=c(13,8.2))
  svg(paste0(nm,'.svg'),width=wh[1],height=wh[2],family='sans',bg='white'); fun(); dev.off()
  png(file.path('previews',paste0(nm,'.png')),width=wh[1],height=wh[2],units='in',res=140,type='cairo'); fun(); dev.off()
}

safe_predict <- function(mm,which='lower') {
  z <- if(which=='lower') mm$lower.predict else mm$upper.predict
  if(length(z) && is.finite(z[1])) exp(z[1]) else NA_real_
}
model_row <- function(mm,group,model) {
  random <- model!='Fixed effect'
  data.frame(group=group,model=model,k=mm$k,
    HR=exp(if(random) mm$TE.random else mm$TE.common),
    lower=exp(if(random) mm$lower.random else mm$lower.common),
    upper=exp(if(random) mm$upper.random else mm$upper.common),
    p=if(random) mm$pval.random else mm$pval.common,
    Q=mm$Q,Q_df=mm$df.Q,Q_p=mm$pval.Q,I2_percent=100*mm$I2,tau2=mm$tau2,
    prediction_lower=if(random) safe_predict(mm,'lower') else NA_real_,
    prediction_upper=if(random) safe_predict(mm,'upper') else NA_real_)
}
results <- rbind(
  model_row(m,'All 7 studies','Random effects REML (Wald)'),
  model_row(m,'All 7 studies','Fixed effect'),
  model_row(m_hk,'All 7 studies','Random effects REML (modified HK)'),
  model_row(m_cox,'Cox cause-specific HR','Random effects REML (Wald)'),
  model_row(m_fg,'Fine-Gray subdistribution HR','Random effects REML (Wald)'),
  model_row(m_fleming_pre,'Fleming pre-stage sensitivity','Random effects REML (Wald)'))
write.csv(results,'model_results.csv',row.names=FALSE)
write.csv(data.frame(method='HTS (t, k-2 df)',k=nrow(d),df=m$df.predict,level=0.95,
  HR=exp(m$TE.random),PI_lower=exp(m$lower.predict),PI_upper=exp(m$upper.predict)),
  'prediction_interval.csv',row.names=FALSE)
write.csv(data.frame(test=c('Egger intercept t test','Begg rank correlation'),k=nrow(d),
  estimate=c(eg[1],begg$tau),statistic=c(eg[3],NA),df=c(nrow(d)-2,NA),p=c(eg[4],begg$pval),
  lower=c(eg_ci[1],NA),upper=c(eg_ci[2],NA),
  interpretation='Exploratory because fewer than 10 studies'),
  'bias_tests.csv',row.names=FALSE)
write.csv(data.frame(contrast='Fine-Gray vs Cox',coefficient=coef(estimand_meta_regression)[2],
  ratio_of_HRs=exp(coef(estimand_meta_regression)[2]),QM=estimand_meta_regression$QM,
  df=estimand_meta_regression$m,QMp=estimand_meta_regression$QMp),
  'estimand_subgroup_test.csv',row.names=FALSE)
write.csv(data.frame(cancer=target_titles,studies=subgroup_counts,displayed=FALSE),
  'subgroup_eligibility.csv',row.names=FALSE)
writeLines(c('None of the seven HR-ready studies belongs to the six prespecified cancer categories.',
  'Prespecified cancers: breast, leukemia, prostate, lung, pancreatic and ovarian cancer.',
  'No prespecified cancer subgroup pooled estimate or subgroup SVG was generated.'),'subgroups_not_estimable.txt')
d$weight_fixed_percent <- 100*m$w.common/sum(m$w.common)
d$weight_random_percent <- 100*m$w.random/sum(m$w.random)
write.csv(d,'analysis_input_with_weights.csv',row.names=FALSE,fileEncoding='UTF-8')
write.csv(d[,c('study_id','author','year','cancer','effect_model','raw_HR','raw_lower','raw_upper',
  'raw_comparison','target_comparison','analysis_origin','HR','lower','upper','selection_reason','source_location')],
  'selection_and_direction_decisions.csv',row.names=FALSE,fileEncoding='UTF-8')
write.csv(loo,'leave_one_out.csv',row.names=FALSE)
saveRDS(list(input=d,meta=m,modified_HK=m_hk,cox=m_cox,fine_gray=m_fg,
  estimand_meta_regression=estimand_meta_regression,fleming_pre_stage=m_fleming_pre,
  egger=egger_fit,begg=begg,leave_one_out=loo),'analysis_objects.rds')
capture.output(print(m),print(m_hk),print(m_cox),print(m_fg),print(m_fleming_pre),
  print(estimand_meta_regression),summary(egger_fit),print(begg),print(loo),file='statistical_output.txt')
capture.output(sessionInfo(),file='sessionInfo.txt')
writeLines(c(paste('Completed:',Sys.time()),paste('RSTUDIO:',Sys.getenv('RSTUDIO')),
  paste('RStudio API:',if(requireNamespace('rstudioapi',quietly=TRUE)) rstudioapi::isAvailable() else FALSE),
  paste('PID:',Sys.getpid()),paste('Working directory:',getwd()),
  paste('Source MD5:',tools::md5sum('analysis.R'))),'execution_record.txt')

report <- c(
  '卫生人力短缺与癌症特异性死亡/生存：HR Meta分析',
  paste0('完成日期：',format(Sys.Date(),'%Y-%m-%d')),
  '',
  '一、分析范围',
  '纳入7篇可提供精确HR及95%CI的独立研究，每篇仅计权一次。结局为癌症特异性死亡或癌症特异性生存。',
  'Russell 2011仅报告多个模型HR范围而无模型特异95%CI；Eide 2009仅报告log-odds及SE，均未进入HR合并。',
  '主分析统一为较低卫生人力可及性相对较高可及性。5篇原文为反方向，使用HR*=1/HR、下限*=1/原上限、上限*=1/原下限；原始值均保留。',
  '',
  '二、效应量选择',
  '每项研究优先选择完整队列、调整最充分、极端类别对比；同一队列的其他模型、职业类别和亚组不重复计权。',
  'Fleming 2018主分析采用含分期的最充分调整模型，并用未调整分期模型进行选择敏感性分析。',
  'Gadkaree 2021选最高与零耳鼻喉科医师密度；McDow 2022选每减少1名内分泌科医师/10万人；Haas 2011选完整队列的低与高外科医师容量。',
  '',
  '三、统计方法',
  'logHR=ln(HR)，SE=[ln(CI上限)-ln(CI下限)]/(2×1.959964)。采用逆方差合并，随机效应REML为主，固定效应为对照，并报告改良Hartung-Knapp敏感性区间。',
  '森林图显示95%预测区间。另进行逐一剔除、Cox与Fine-Gray分层敏感性以及Fleming模型选择敏感性分析。',
  '漏斗图、Egger截距检验和Begg检验仅作探索；k=7时检验效能有限。',
  '',
  '四、总体结果',
  sprintf('随机效应REML：HR=%.3f，95%%CI %.3f–%.3f，P%s。',exp(m$TE.random),exp(m$lower.random),exp(m$upper.random),pf(m$pval.random)),
  sprintf('固定效应：HR=%.3f，95%%CI %.3f–%.3f，P%s。',exp(m$TE.common),exp(m$lower.common),exp(m$upper.common),pf(m$pval.common)),
  sprintf('异质性：I²=%.1f%%，tau²=%.5f，Q=%.3f，df=%d，P%s。',100*m$I2,m$tau2,m$Q,m$df.Q,pf(m$pval.Q)),
  sprintf('95%%预测区间：%.3f–%.3f。',exp(m$lower.predict),exp(m$upper.predict)),
  sprintf('改良Hartung-Knapp：HR=%.3f，95%%CI %.3f–%.3f，P%s。',exp(m_hk$TE.random),exp(m_hk$lower.random),exp(m_hk$upper.random),pf(m_hk$pval.random)),
  '',
  '五、敏感性与小样本效应',
  sprintf('Cox研究（k=%d）：HR=%.3f，95%%CI %.3f–%.3f。',m_cox$k,exp(m_cox$TE.random),exp(m_cox$lower.random),exp(m_cox$upper.random)),
  sprintf('Fine-Gray研究（k=%d）：HR=%.3f，95%%CI %.3f–%.3f。',m_fg$k,exp(m_fg$TE.random),exp(m_fg$lower.random),exp(m_fg$upper.random)),
  sprintf('Fleming采用分期前模型时：HR=%.3f，95%%CI %.3f–%.3f。',exp(m_fleming_pre$TE.random),exp(m_fleming_pre$lower.random),exp(m_fleming_pre$upper.random)),
  sprintf('Egger截距=%.3f，95%%CI %.3f–%.3f，t=%.3f，df=5，P%s。',eg[1],eg_ci[1],eg_ci[2],eg[3],pf(eg[4])),
  sprintf('Begg Kendall tau=%.3f，P%s。',begg$tau,pf(begg$pval)),
  '',
  '六、解释限制',
  '不同研究的人力暴露单位和对比尺度不相同，包括短缺地区、密度类别、空间可及性分位数和每减少1名专科医师。总体合并是方向统一后的探索性关联。',
  'Cox原因别HR与Fine-Gray亚分布HR含义不同，主分析合并结果需结合分层敏感性分析解释。',
  '当前7篇研究均不属于预设六癌种，因此未生成六癌种亚组图。',
  '',
  '七、输出',
  'forest.svg：总体森林图并含95%预测区间；funnel.svg：漏斗图；egger.svg：Egger回归图；leave_one_out.svg：逐一剔除图。',
  'analysis.R：完整统计及绘图代码；included_HR_cancer_specific.csv：原始HR输入；selection_and_direction_decisions.csv：本次效应量选择及方向转换。',
  'model_results.csv、prediction_interval.csv、bias_tests.csv、leave_one_out.csv和estimand_subgroup_test.csv保存未取整结果。'
)
writeLines(report,'分析报告与复现说明.txt',useBytes=TRUE)
print(results)
cat('\nCancer-specific mortality workforce meta-analysis and four SVG figures completed.\n')
