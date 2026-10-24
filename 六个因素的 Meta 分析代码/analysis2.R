# Diagnostic delay and cancer-specific mortality/survival: categorical HRs.
# Open this script in RStudio and click Source. Outputs are genuine vector SVGs.
# Plot style follows HR_Meta_Analysis_2026-10-10/analysis.R.
# No >=4-week restriction; quartile and continuous-increment contrasts excluded.

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
stopifnot(nrow(d)==4L,!anyDuplicated(d$cohort),
          all(d$lower>0 & d$lower<d$HR & d$HR<d$upper),
          !any(grepl('quartile|Q[1-4]',d$comparison,ignore.case=TRUE)))
d$study <- paste(d$author,d$year)
d$logHR <- log(d$HR)
d$SE <- (log(d$upper)-log(d$lower))/(2*qnorm(.975))
d$point_label <- paste0(d$study,'\nHR = ',formatC(d$HR,format='f',digits=3))

fit_meta <- function(z,ci='classic') metagen(TE=logHR,seTE=SE,studlab=study,data=z,sm='HR',
  common=TRUE,random=TRUE,method.tau='REML',method.random.ci=ci,
  adhoc.hakn.ci=if(ci=='HK') 'se' else '',prediction=nrow(z)>=3,method.predict='HTS',
  control=list(stepadj=.25,maxiter=10000))
m <- fit_meta(d)
m_hk <- fit_meta(d,'HK')
rma_check <- rma(yi=d$logHR,sei=d$SE,method='REML',test='z',
  control=list(stepadj=.25,maxiter=10000))
stopifnot(abs(as.numeric(rma_check$b)-m$TE.random)<1e-5,
          abs(rma_check$tau2-m$tau2)<1e-5)

loo_raw <- as.data.frame(leave1out(rma_check,transf=exp))
loo <- data.frame(omitted_id=d$study_id,omitted_study=d$study,
  HR=loo_raw$estimate,lower=loo_raw$ci.lb,upper=loo_raw$ci.ub,
  p=loo_raw$pval,tau2=loo_raw$tau2,
  I2_percent=100*pmax(0,(loo_raw$Q-(nrow(d)-2))/loo_raw$Q))

# Small-study tests are computed for completeness, but k=4 gives very low power.
egger_fit <- lm(I(logHR/SE) ~ I(1/SE),data=d)
eg <- coef(summary(egger_fit))[1,]
eg_ci <- confint(egger_fit)[1,]
eg_check <- regtest(d$logHR,sei=d$SE,model='lm',predictor='sei')
stopifnot(isTRUE(all.equal(unname(eg[4]),eg_check$pval,tolerance=1e-8)))
begg <- ranktest(d$logHR,vi=d$SE^2)
pf <- function(x) ifelse(is.na(x),'NA',ifelse(x<.001,'< 0.001',paste0('= ',formatC(x,format='f',digits=3))))

target_cancers <- c('breast cancer','leukemia','prostate cancer','lung cancer','pancreatic cancer','ovarian cancer')
target_titles <- c('Breast Cancer','Leukemia','Prostate Cancer','Lung Cancer','Pancreatic Cancer','Ovarian Cancer')
subgroup_counts <- vapply(target_cancers,function(x) sum(d$cancer==x),integer(1))
stopifnot(all(subgroup_counts==0L))

draw_forest <- function() {
  mp <- m
  mp$lower <- log(d$lower); mp$upper <- log(d$upper)
  forest(mp,leftcols=c('studlab','TE','seTE'),leftlabs=c('Study','logHR','SE(logHR)'),
    rightcols=c('effect','ci','w.common','w.random'),
    rightlabs=c('HR','95% CI','Weight\n(fixed)','Weight\n(random)'),
    text.common='Fixed effect',text.random='Random effects (REML)',
    xlab='Hazard ratio (longer vs shorter diagnostic interval)',
    smlab='Cancer-specific mortality / survival',
    col.square='grey65',col.square.lines='grey30',col.diamond.common='black',
    col.diamond.random='firebrick3',col.predict='royalblue3',
    print.I2=TRUE,print.tau2=TRUE,print.Q=TRUE,print.pval.Q=TRUE,
    test.overall.common=TRUE,test.overall.random=TRUE,prediction=TRUE,
    fontsize=10,digits=3,digits.se=4,digits.tau2=4,
    label.left='Lower cancer-specific mortality hazard',
    label.right='Higher cancer-specific mortality hazard',
    addrows.below.overall=5,xlim=c(.2,12),at=c(.25,.5,1,2,4,8))
}

side_labels <- function(x,y,labels,left,xleft,xright,ylo,yhi,cex=.82) {
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
  lim <- core+c(-.62,.62)*span
  plot(NA,xlim=lim,ylim=c(ymax,0),xlab='Hazard ratio (logarithmic scale)',
    ylab='Standard error of log(HR)',xaxt='n',
    main='Funnel plot: diagnostic delay and cancer-specific mortality')
  ticks <- c(.1,.25,.5,1,2,4,10); ticks <- ticks[log(ticks)>lim[1] & log(ticks)<lim[2]]
  axis(1,at=log(ticks),labels=ticks)
  polygon(c(center,center-qnorm(.975)*ymax,center+qnorm(.975)*ymax),
    c(0,ymax,ymax),col='grey94',border=NA)
  abline(v=center,lty=2,col='firebrick3')
  lines(center-qnorm(.975)*c(0,ymax),c(0,ymax),lty=3)
  lines(center+qnorm(.975)*c(0,ymax),c(0,ymax),lty=3)
  side_labels(d$logHR,d$SE,d$point_label,d$logHR<center,
    core[1]-.04*span,core[2]+.04*span,.06*ymax,.76*ymax)
  points(d$logHR,d$SE,pch=21,bg='grey65',cex=1.4)
  mtext(paste0('Egger intercept test: P ',pf(eg[4]),' (k = 4; df = 2)'),side=3,line=.5)
  mtext('Very low power with four studies; asymmetry is not proof of publication bias',side=1,line=3.7,cex=.85)
  legend('bottomleft',legend=c('Fixed-effect centre','Pseudo 95% confidence limits'),
    lty=c(2,3),col=c('firebrick3','black'),bty='n',cex=.85)
}

draw_egger <- function() {
  par(mar=c(5.5,5,5,2))
  prec <- 1/d$SE; snd <- d$logHR/d$SE
  xr <- range(prec); span <- diff(xr); lim <- c(-.35*span,max(prec)+.45*span)
  yr <- range(c(0,snd,eg[1])); yr <- yr+c(-.22,.25)*diff(yr)
  plot(NA,xlim=lim,ylim=yr,xaxt='n',xlab='Precision: 1 / SE(log HR)',
    ylab='Standard normal deviate: log HR / SE',
    main='Egger regression: diagnostic delay and cancer-specific mortality')
  ticks <- pretty(c(0,max(prec))); ticks <- ticks[ticks>=0 & ticks<=max(prec)*1.1]
  axis(1,at=ticks,labels=ticks)
  segments(0,coef(egger_fit)[1],max(prec)*1.04,
    coef(egger_fit)[1]+coef(egger_fit)[2]*max(prec)*1.04,col='firebrick3',lwd=2)
  abline(h=0,lty=3,col='grey60')
  side_labels(prec,snd,d$point_label,prec<=median(prec),
    -.025*span,max(prec)+.025*span,yr[1]+.12*diff(yr),yr[2]-.1*diff(yr))
  points(prec,snd,pch=21,bg='grey65',cex=1.4)
  mtext(sprintf('Intercept = %.3f; t = %.3f; df = 2; P %s',eg[1],eg[3],pf(eg[4])),side=3,line=.5)
  mtext('Exploratory only because k = 4',side=1,line=3.7,cex=.85)
}

draw_leave_one_out <- function() {
  par(mar=c(3,1.5,2,1.5),family='sans')
  plot.new(); plot.window(xlim=c(0,1),ylim=c(-1.3,7.7))
  title('Leave-one-out sensitivity analysis',line=.1,cex.main=1.25)
  text(.5,7.15,'Random-effects REML | Cancer-specific mortality / survival',cex=.84,col='grey35')
  text(.025,6.4,'Omitted study',adj=0,font=2,cex=.86)
  text(.56,6.4,'Pooled hazard ratio',font=2,cex=.86)
  text(.805,6.4,'HR [95% CI]',font=2,cex=.86)
  text(.955,6.4,'I2',font=2,cex=.86)
  segments(.02,6.05,.985,6.05,col='grey45')
  plot_min <- min(c(loo$lower,exp(m$lower.random)))
  plot_max <- max(c(loo$upper,exp(m$upper.random)))
  lo <- max(.15,floor(plot_min*10)/10); hi <- ceiling(plot_max*10)/10
  xx <- function(hr) .43+(log(hr)-log(lo))/(log(hi)-log(lo))*.27
  yy <- 5.3:2.3
  for(i in seq_len(nrow(loo))) {
    y <- yy[i]
    if(i%%2==0) rect(.02,y-.36,.985,y+.36,col='grey96',border=NA)
    segments(xx(1),y-.36,xx(1),y+.36,col='grey70',lty=2)
    text(.025,y,paste0('Omit ',loo$omitted_study[i]),adj=0,cex=.82)
    segments(xx(loo$lower[i]),y,xx(loo$upper[i]),y,lwd=1.35,col='grey25')
    segments(xx(loo$lower[i]),y-.1,xx(loo$lower[i]),y+.1,col='grey25')
    segments(xx(loo$upper[i]),y-.1,xx(loo$upper[i]),y+.1,col='grey25')
    points(xx(loo$HR[i]),y,pch=22,bg='grey65',col='grey30',cex=1.35)
    text(.805,y,sprintf('%.3f [%.3f, %.3f]',loo$HR[i],loo$lower[i],loo$upper[i]),cex=.79)
    text(.955,y,sprintf('%.1f%%',loo$I2_percent[i]),cex=.79)
  }
  segments(.02,1.65,.985,1.65,col='grey45')
  text(.025,1.05,'All 4 studies',adj=0,font=2,cex=.85)
  xmid <- xx(exp(m$TE.random)); xlow <- xx(exp(m$lower.random)); xhigh <- xx(exp(m$upper.random))
  polygon(c(xlow,xmid,xhigh,xmid),c(1.05,1.23,1.05,.87),col='firebrick3',border='firebrick3')
  text(.805,1.05,sprintf('%.3f [%.3f, %.3f]',exp(m$TE.random),exp(m$lower.random),exp(m$upper.random)),cex=.79,font=2)
  text(.955,1.05,sprintf('%.1f%%',100*m$I2),cex=.79,font=2)
  segments(xx(lo),.2,xx(hi),.2,col='grey30')
  ticks <- exp(pretty(log(c(lo,hi)),5)); ticks <- ticks[ticks>=lo & ticks<=hi]
  for(v in ticks) {segments(xx(v),.2,xx(v),.08,col='grey30');text(xx(v),-.15,formatC(v,digits=2,format='fg'),cex=.76)}
  text(.56,-.7,'Hazard ratio (longer vs shorter interval)',cex=.82)
}

for(nm in c('forest','funnel','egger','leave_one_out')) {
  fun <- get(paste0('draw_',nm))
  wh <- switch(nm,forest=c(13,7),funnel=c(12,8),egger=c(12,8),leave_one_out=c(13,7))
  svg(paste0(nm,'.svg'),width=wh[1],height=wh[2],family='sans',bg='white'); fun(); dev.off()
  png(file.path('previews',paste0(nm,'.png')),width=wh[1],height=wh[2],units='in',res=140,type='cairo'); fun(); dev.off()
}

model_row <- function(mm,group,model) {
  random <- model!='Fixed effect'
  data.frame(group=group,model=model,k=mm$k,
    HR=exp(if(random) mm$TE.random else mm$TE.common),
    lower=exp(if(random) mm$lower.random else mm$lower.common),
    upper=exp(if(random) mm$upper.random else mm$upper.common),
    p=if(random) mm$pval.random else mm$pval.common,
    Q=mm$Q,Q_df=mm$df.Q,Q_p=mm$pval.Q,I2_percent=100*mm$I2,tau2=mm$tau2,
    prediction_lower=if(random && !is.null(mm$lower.predict)) exp(mm$lower.predict) else NA,
    prediction_upper=if(random && !is.null(mm$upper.predict)) exp(mm$upper.predict) else NA)
}
results <- rbind(model_row(m,'All 4 studies','Random effects REML (Wald)'),
  model_row(m,'All 4 studies','Fixed effect'),
  model_row(m_hk,'All 4 studies','Random effects REML (modified HK)'))
write.csv(results,'model_results.csv',row.names=FALSE)
write.csv(data.frame(test=c('Egger intercept t test','Begg rank correlation'),k=4,
  estimate=c(eg[1],begg$tau),statistic=c(eg[3],NA),df=c(2,NA),p=c(eg[4],begg$pval),
  lower=c(eg_ci[1],NA),upper=c(eg_ci[2],NA)),
  'bias_tests.csv',row.names=FALSE)
write.csv(data.frame(cancer=target_titles,studies=subgroup_counts,displayed=FALSE),
  'subgroup_eligibility.csv',row.names=FALSE)
writeLines(c('No eligible cancer-specific mortality/survival studies belong to the six prespecified cancer subgroups.',
  'Prespecified cancers: breast, leukemia, prostate, lung, pancreatic and ovarian cancer.',
  'No subgroup pooled estimate or subgroup SVG was generated.'),'subgroups_not_estimable.txt')
d$weight_fixed_percent <- 100*m$w.common/sum(m$w.common)
d$weight_random_percent <- 100*m$w.random/sum(m$w.random)
write.csv(d,'analysis_input_with_weights.csv',row.names=FALSE,fileEncoding='UTF-8')
write.csv(loo,'leave_one_out.csv',row.names=FALSE)
saveRDS(list(input=d,meta=m,modified_HK=m_hk,egger=egger_fit,begg=begg,
  leave_one_out=loo),'analysis_objects.rds')
capture.output(print(m),print(m_hk),summary(egger_fit),print(begg),print(loo),
  file='statistical_output.txt')
capture.output(sessionInfo(),file='sessionInfo.txt')
writeLines(c(paste('Completed:',Sys.time()),paste('RSTUDIO:',Sys.getenv('RSTUDIO')),
  paste('RStudio API:',if(requireNamespace('rstudioapi',quietly=TRUE)) rstudioapi::isAvailable() else FALSE),
  paste('PID:',Sys.getpid()),paste('Working directory:',getwd()),
  paste('Source MD5:',tools::md5sum('analysis.R'))),'execution_record.txt')

report <- c(
  '诊断延迟与癌症特异性死亡/生存：HR Meta分析',
  paste0('完成日期：',format(Sys.Date(),'%Y-%m-%d')),
  '',
  '一、分析范围',
  '纳入4篇研究，每篇一个癌症特异性死亡或癌症特异性生存HR。比较方向均为较长诊断间隔相对明确较短参照组。',
  '不设>=4周门槛，排除四分位比较、连续增量HR和参照编码不明确的HR。',
  '4篇均已存在于原14篇全因死亡/总生存数据集中，因此新增效应量4个，新增独立研究0篇。',
  '',
  '二、统计方法',
  '输入为原文HR及95%CI。logHR=ln(HR)，SE=[ln(CI上限)-ln(CI下限)]/(2×1.959964)。',
  '采用逆方差合并；随机效应REML为主，固定效应为对照；另报告改良Hartung-Knapp敏感性区间。',
  '发表偏倚/小样本效应使用漏斗图、Egger截距t检验和Begg秩相关检验。仅4篇研究，检验能力极低。',
  '',
  '三、总体结果',
  sprintf('随机效应REML：HR=%.3f，95%%CI %.3f–%.3f，P%s。',exp(m$TE.random),exp(m$lower.random),exp(m$upper.random),pf(m$pval.random)),
  sprintf('固定效应：HR=%.3f，95%%CI %.3f–%.3f，P%s。',exp(m$TE.common),exp(m$lower.common),exp(m$upper.common),pf(m$pval.common)),
  sprintf('异质性：I²=%.1f%%，tau²=%.5f，Q=%.3f，df=%d，P%s。',100*m$I2,m$tau2,m$Q,m$df.Q,pf(m$pval.Q)),
  sprintf('95%%预测区间：%.3f–%.3f。',exp(m$lower.predict),exp(m$upper.predict)),
  sprintf('改良Hartung-Knapp：HR=%.3f，95%%CI %.3f–%.3f，P%s。',exp(m_hk$TE.random),exp(m_hk$lower.random),exp(m_hk$upper.random),pf(m_hk$pval.random)),
  '',
  '四、发表偏倚/小样本效应',
  sprintf('Egger截距=%.3f，95%%CI %.3f–%.3f，t=%.3f，df=2，P%s。',eg[1],eg_ci[1],eg_ci[2],eg[3],pf(eg[4])),
  sprintf('Begg Kendall tau=%.3f，P%s。',begg$tau,pf(begg$pval)),
  '由于k=4，无论检验是否显著，都不能据此排除或确认发表偏倚。',
  '',
  '五、癌种亚组',
  '先前限定的六种癌症为乳腺癌、白血病、前列腺癌、肺癌、胰腺癌和卵巢癌。4篇癌症特异性研究均不属于这些癌种。',
  '因此六癌种亚组分析无法估计，也未生成空白亚组图。',
  '',
  '六、解释',
  '本结果为不同癌种和不同诊断延迟阈值的探索性关联合并，不能解释为每4周延迟效应。',
  '全因死亡HR和癌症特异性死亡HR代表不同结局。同一队列的两个结局不能作为两个独立研究在同一次Meta分析中重复加权。',
  '',
  '七、输出',
  'forest.svg：总体森林图；funnel.svg：漏斗图；egger.svg：Egger回归图；leave_one_out.svg：逐一剔除敏感性图。',
  'analysis.R：全部统计及绘图代码；included_HR_cancer_specific.csv：输入数据；model_results.csv与bias_tests.csv：未取整结果。'
)
writeLines(report,'分析报告与复现说明.txt',useBytes=TRUE)
print(results)
cat('\nCancer-specific mortality meta-analysis and four SVG figures completed.\n')
