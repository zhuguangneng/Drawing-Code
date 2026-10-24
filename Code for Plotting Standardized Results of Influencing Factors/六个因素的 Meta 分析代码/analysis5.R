# Particulate exposure and post-diagnosis mortality: per 10 ug/m3 HR.
# Adapted visual style from Delayed diagnosis/HR_Meta_Analysis_2026-10-10/analysis.R.
# 6 articles; retain different reports from overlapping cohorts per user specification.
# This is exploratory; different particles/cancer-death definitions/windows are pooled by user request.
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

d <- read.csv('included_HR.csv',fileEncoding='UTF-8-BOM',check.names=FALSE)
stopifnot(nrow(d)==6L,!anyDuplicated(d$study_id),
          all(d$original_lower>0 & d$original_lower<d$original_HR & d$original_HR<d$original_upper),
          all(d$increment>0),all(d$target_increment==10))
d$HR <- d$original_HR^(10/d$increment)
d$lower <- d$original_lower^(10/d$increment)
d$upper <- d$original_upper^(10/d$increment)
d$study <- paste(d$author,d$year)
d$logHR <- log(d$HR)
d$SE <- (log(d$upper)-log(d$lower))/3.92
d$point_label <- paste0(d$study,'\nHR = ',sprintf('%.3f',d$HR))

# Classic Wald CI matches the reference theme. Modified Hartung-Knapp sensitivity
# is reported separately, especially because the cancer subgroups are very small.
fit_meta <- function(z,ci='classic') metagen(TE=logHR,seTE=SE,studlab=study,data=z,sm='HR',
   common=TRUE,random=TRUE,method.tau='REML',method.random.ci=ci,
   adhoc.hakn.ci=if(ci=='HK') 'se' else '',prediction=nrow(z)>=3,method.predict='HTS')
m <- fit_meta(d)
m_hk <- fit_meta(d,'HK')
m_index <- fit_meta(subset(d,!study_id %in% c('S11','S45')))
m_strict <- fit_meta(subset(d,!study_id %in% c('S02','S11','S45')))
m_linear <- fit_meta(subset(d,!study_id %in% c('S13','S56')))
m_model_clear <- fit_meta(subset(d,study_id!='S02'))
# Independent numerical verification of the primary REML fit.
rma_check <- rma(yi=d$logHR,sei=d$SE,method='REML',test='z')
stopifnot(abs(as.numeric(rma_check$b)-m$TE.random)<1e-5,
          abs(rma_check$tau2-m$tau2)<1e-5)
loo_raw <- as.data.frame(leave1out(rma_check,transf=exp))
stopifnot(nrow(loo_raw)==nrow(d),all(loo_raw$ci.lb>0),
          all(loo_raw$ci.lb<loo_raw$estimate & loo_raw$estimate<loo_raw$ci.ub))
loo <- data.frame(omitted_id=d$study_id,omitted_study=d$study,
                  HR=loo_raw$estimate,lower=loo_raw$ci.lb,upper=loo_raw$ci.ub,
                  p=loo_raw$pval,tau2=loo_raw$tau2,
                  I2_percent=100*pmax(0,(loo_raw$Q-(nrow(d)-2))/loo_raw$Q))

# Egger: standardized normal deviate regressed on precision; intercept t test.
egger_fit <- lm(I(logHR/SE) ~ I(1/SE),data=d)
eg <- coef(summary(egger_fit))[1,]
eg_ci <- confint(egger_fit)[1,]
eg_check <- regtest(d$logHR,sei=d$SE,model='lm',predictor='sei')
stopifnot(isTRUE(all.equal(unname(eg[4]),eg_check$pval,tolerance=1e-8)))
begg <- ranktest(d$logHR,vi=d$SE^2)
pf <- function(x) ifelse(is.na(x),'NA',ifelse(x<.001,'< 0.001',paste0('= ',formatC(x,format='f',digits=3))))

# Only these six Figure-5 cancers are eligible for subgroup display.
target_cancers <- c('breast cancer','leukemia','prostate cancer','lung cancer','pancreatic cancer','ovarian cancer')
target_titles <- c('Breast Cancer','Leukemia','Prostate Cancer','Lung Cancer','Pancreatic Cancer','Ovarian Cancer')
subsets <- lapply(target_cancers,function(x) d[d$cancer==x,,drop=FALSE])
names(subsets) <- target_titles
subsets <- subsets[lengths(lapply(subsets, function(z) z$study_id))>0]
stopifnot(identical(vapply(subsets,nrow,integer(1)),c('Breast Cancer'=3L)))
submodels <- lapply(subsets,function(z) if(nrow(z)>1) fit_meta(z) else NULL)
submodels_hk <- lapply(subsets,function(z) if(nrow(z)>1) fit_meta(z,'HK') else NULL)
sd <- do.call(rbind,subsets)
sd$cancer <- factor(sd$cancer,levels=target_cancers[target_cancers %in% sd$cancer])
# Exploratory omnibus test among observed target cancers, with common residual tau2.
# Three breast-cancer reports; no other target subgroup available.
subgroup_test <- NULL # Only one eligible cancer subgroup; no between-cancer test.

draw_forest <- function() {
  mp <- m
  mp$lower <- log(d$lower); mp$upper <- log(d$upper) # preserve published, rounded CIs
  forest(mp,leftcols=c('studlab','TE','seTE'),leftlabs=c('Study','logHR','SE(logHR)'),
    rightcols=c('effect','ci','w.common','w.random'),
    rightlabs=c('HR','95% CI','Weight\n(fixed)','Weight\n(random)'),
    text.common='Fixed effect',text.random='Random effects (REML)',
    xlab='Hazard ratio (per 10 ug/m3 higher concentration)',
    smlab='Cancer-specific mortality',
    col.square='grey65',col.square.lines='grey30',col.diamond.common='black',
    col.diamond.random='firebrick3',col.predict='royalblue3',
    print.I2=TRUE,print.tau2=TRUE,print.Q=TRUE,print.pval.Q=TRUE,
    test.overall.common=TRUE,test.overall.random=TRUE,prediction=TRUE,
    fontsize=10,digits=3,digits.se=4,digits.tau2=4,
    label.left='Lower mortality hazard',label.right='Higher mortality hazard',
    addrows.below.overall=5,xlim=c(.25,16),at=c(.25,.5,1,2,4,8,16))
}

# Place labels in two ordered side columns to retain author/year/HR labels
# without overlap in the six-study version of the reference plots.
side_labels <- function(x,y,labels,left,xleft,xright,ylo,yhi,cex=.75) {
  for(side in c(TRUE,FALSE)) {
    ix <- which(left==side)
    if(!length(ix)) next
    ix <- ix[order(y[ix])]
    yy <- seq(ylo,yhi,length.out=length(ix))
    xx <- if(side) xleft else xright
    segments(x[ix],y[ix],xx,yy,col='grey75',lwd=.7)
    # White label backing keeps guide lines and the zero line out of text.
    ww <- strwidth(labels[ix],cex=cex)
    hh <- strheight(labels[ix],cex=cex)
    pad <- .004*diff(par('usr')[1:2])
    rect(if(side) xx-ww-pad else xx-pad,yy-hh*.57,
         if(side) xx+pad else xx+ww+pad,yy+hh*.57,col='white',border=NA)
    text(xx,yy,labels[ix],adj=if(side) c(1,.5) else c(0,.5),cex=cex)
  }
}
draw_funnel <- function() {
  par(mar=c(5.5,5,5,2))
  ymax <- max(d$SE)*1.22; center <- m$TE.common
  core <- range(c(d$logHR,center+c(-1,1)*qnorm(.975)*ymax))
  span <- diff(core); lim <- core+c(-.72,.72)*span
  plot(NA,xlim=lim,ylim=c(ymax,0),xlab='Hazard ratio (logarithmic scale)',
       ylab='Standard error of log(HR)',xaxt='n',main='Funnel plot: particulate exposure and cancer mortality')
  ticks <- c(.1,.25,.5,1,2,4,10); ticks <- ticks[log(ticks)>lim[1] & log(ticks)<lim[2]]
  axis(1,at=log(ticks),labels=ticks)
  polygon(c(center,center-qnorm(.975)*ymax,center+qnorm(.975)*ymax),
          c(0,ymax,ymax),col='grey94',border=NA)
  abline(v=center,lty=2,col='firebrick3')
  lines(center-qnorm(.975)*c(0,ymax),c(0,ymax),lty=3)
  lines(center+qnorm(.975)*c(0,ymax),c(0,ymax),lty=3)
  side_labels(d$logHR,d$SE,d$point_label,d$logHR<center,
              core[1]-.05*span,core[2]+.05*span,.035*ymax,.79*ymax)
  points(d$logHR,d$SE,pch=21,bg='grey65',cex=1.3)
  mtext(paste0('Egger intercept test: P ',pf(eg[4]),' (k = 6; df = 4; exploratory)'),side=3,line=.5)
  mtext('Only 6 studies: low power; asymmetry can also reflect heterogeneity',side=1,line=3.7,cex=.85)
  legend('bottomleft',legend=c('Fixed-effect centre','Pseudo 95% confidence limits'),
         lty=c(2,3),col=c('firebrick3','black'),bty='n',cex=.85)
}
draw_egger <- function() {
  par(mar=c(5.5,5,5,2))
  prec <- 1/d$SE; snd <- d$logHR/d$SE
  xr <- range(prec); span <- diff(xr)
  lim <- c(-.65*span,max(prec)+.7*span)
  yr <- range(c(0,snd,eg[1])); yr <- yr+c(-.2,.22)*diff(yr)
  plot(NA,xlim=lim,ylim=yr,xaxt='n',xlab='Precision: 1 / SE(log HR)',
       ylab='Standard normal deviate: log HR / SE',main='Egger regression: particulate exposure and cancer mortality')
  ticks <- pretty(c(0,max(prec))); ticks <- ticks[ticks>=0 & ticks<=max(prec)*1.1]
  axis(1,at=ticks,labels=ticks)
  segments(0,coef(egger_fit)[1],max(prec)*1.04,
           coef(egger_fit)[1]+coef(egger_fit)[2]*max(prec)*1.04,col='firebrick3',lwd=2)
  abline(h=0,lty=3,col='grey60')
  # Split near the median precision; label lines are only visual guides.
  side_labels(prec,snd,d$point_label,prec<=median(prec),
              -.04*span,max(prec)+.04*span,yr[1]+.12*diff(yr),yr[2]-.1*diff(yr))
  points(prec,snd,pch=21,bg='grey65',cex=1.3)
  mtext(sprintf('Intercept = %.3f; t = %.3f; df = 4; P %s',eg[1],eg[3],pf(eg[4])),side=3,line=.5)
  mtext('Exploratory only (k < 10); not proof of presence or absence of publication bias',side=1,line=3.7,cex=.85)
}

# Leave-one-out sensitivity plot: refit the same REML random-effects model after
# omitting each study. The bottom diamond is the unchanged 6-study reference.
draw_leave_one_out <- function() {
  par(mar=c(3,1.5,2,1.5),family='sans')
  plot.new(); plot.window(xlim=c(0,1),ylim=c(-1.3,9.5))
  title('Leave-one-out sensitivity analysis',line=.1,cex.main=1.25)
  text(.5,8.95,'Random-effects REML | Particulate exposure: per 10 ug/m3',cex=.84,col='grey35')
  text(.025,8,'Omitted study',adj=0,font=2,cex=.86)
  text(.565,8,'Pooled hazard ratio',font=2,cex=.86)
  text(.805,8,'HR [95% CI]',font=2,cex=.86)
  text(.955,8,'I2',font=2,cex=.86)
  segments(.02,7.65,.985,7.65,col='grey45')
  plot_min <- min(c(loo$lower,exp(m$lower.random)))
  plot_max <- max(c(loo$upper,exp(m$upper.random)))
  ticks <- c(.75,1,1.25,1.5,2,2.5,3,4,5)
  lo <- min(.7,floor(plot_min*10)/10)
  hi <- max(1.8,ceiling(plot_max*10)/10)
  xx <- function(hr) .445+(log(hr)-log(lo))/(log(hi)-log(lo))*.255
  yy <- 7:2
  for(i in seq_len(nrow(loo))) {
    y <- yy[i]
    if(i%%2==0) rect(.02,y-.43,.985,y+.43,col='grey96',border=NA)
    segments(xx(1),y-.43,xx(1),y+.43,col='grey70',lty=2)
    text(.025,y,paste0('Omit ',loo$omitted_study[i]),adj=0,cex=.81)
    segments(xx(loo$lower[i]),y,xx(loo$upper[i]),y,lwd=1.35,col='grey25')
    segments(xx(loo$lower[i]),y-.11,xx(loo$lower[i]),y+.11,col='grey25')
    segments(xx(loo$upper[i]),y-.11,xx(loo$upper[i]),y+.11,col='grey25')
    points(xx(loo$HR[i]),y,pch=22,bg='grey65',col='grey30',cex=1.35)
    text(.805,y,sprintf('%.3f [%.3f, %.3f]',loo$HR[i],loo$lower[i],loo$upper[i]),cex=.79)
    text(.955,y,sprintf('%.1f%%',loo$I2_percent[i]),cex=.79)
  }
  segments(.02,1.5,.985,1.5,col='grey45')
  text(.025,.77,'All 6 articles',adj=0,font=2,cex=.85)
  xmid <- xx(exp(m$TE.random)); xlow <- xx(exp(m$lower.random)); xhigh <- xx(exp(m$upper.random))
  polygon(c(xlow,xmid,xhigh,xmid),c(.77,.97,.77,.57),col='firebrick3',border='firebrick3')
  text(.805,.77,sprintf('%.3f [%.3f, %.3f]',exp(m$TE.random),exp(m$lower.random),exp(m$upper.random)),cex=.79,font=2)
  text(.955,.77,sprintf('%.1f%%',100*m$I2),cex=.79,font=2)
  segments(xx(lo),-.05,xx(hi),-.05,col='grey30')
  ticks <- ticks[ticks>=lo & ticks<=hi]
  for(v in ticks) {segments(xx(v),-.05,xx(v),-.19,col='grey30');text(xx(v),-.47,format(v),cex=.76)}
  text(.565,-.98,'Hazard ratio (per 10 ug/m3)',cex=.82)
}

# Vector grid panels reproduce the Figure-5 arrangement and visual vocabulary:
# bordered panels, grey weight-scaled squares, red pooled diamonds, black CIs,
# log-effect/SE columns and fixed/random weights. HR replaces the source's RR.
panel <- function(z,mm,title,letter) {
  grid.roundrect(x=.5,y=.5,width=.985,height=.965,r=unit(.008,'npc'),
                 gp=gpar(fill='white',col='grey45',lwd=.9))
  txt <- function(label,x,y,size=9,bold=FALSE,just='centre',col='black')
    grid.text(label,x=x,y=y,just=just,gp=gpar(fontfamily='sans',fontsize=size,fontface=if(bold) 2 else 1,col=col))
  txt(title,.5,.925,12,TRUE)
  heads <- c('Study','logHR','SE(logHR)','Hazard Ratio','HR','95% CI','Weight\n(fixed)','Weight\n(random)')
  xs <- c(.025,.305,.385,.555,.705,.795,.883,.957)
  for(j in seq_along(heads)) txt(heads[j],xs[j],.827,8.3,TRUE,if(j==1) 'left' else 'centre')
  grid.lines(x=c(.012,.988),y=c(.778,.778),gp=gpar(col='grey35'))
  lo <- .25; hi <- 16; pleft <- .465; pright <- .65
  xp <- function(hr) pleft+(log(hr)-log(lo))/(log(hi)-log(lo))*(pright-pleft)
  grid.lines(x=rep(xp(1),2),y=c(.25,.757),gp=gpar(lty=2,col='grey50'))
  yy <- .715-(seq_len(nrow(z))-1)*.063
  wf <- if(is.null(mm)) 100 else 100*mm$w.common/sum(mm$w.common)
  wr <- if(is.null(mm)) 100 else 100*mm$w.random/sum(mm$w.random)
  for(i in seq_len(nrow(z))) {
    txt(z$study[i],xs[1],yy[i],8.8,just='left')
    txt(sprintf('%.4f',z$logHR[i]),xs[2],yy[i],8.5)
    txt(sprintf('%.4f',z$SE[i]),xs[3],yy[i],8.5)
    grid.lines(x=xp(c(z$lower[i],z$upper[i])),y=rep(yy[i],2),gp=gpar(col='black',lwd=1))
    grid.points(x=xp(z$HR[i]),y=yy[i],pch=22,size=unit(1.6+3.8*sqrt(wr[i]/100),'mm'),
                gp=gpar(fill='grey65',col='grey50'))
    txt(sprintf('%.3f',z$HR[i]),xs[5],yy[i],8.5)
    txt(sprintf('[%.3f; %.3f]',z$lower[i],z$upper[i]),xs[6],yy[i],8.5)
    txt(sprintf('%.1f%%',wf[i]),xs[7],yy[i],8.5)
    txt(sprintf('%.1f%%',wr[i]),xs[8],yy[i],8.5)
  }
  if(!is.null(mm)) {
    for(j in 1:2) {
      y <- .395-(j-1)*.067
      est <- exp(if(j==1) mm$TE.common else mm$TE.random)
      lower <- exp(if(j==1) mm$lower.common else mm$lower.random)
      upper <- exp(if(j==1) mm$upper.common else mm$upper.random)
      txt(if(j==1) 'Common effect model' else 'Random effects model',xs[1],y,9,TRUE,'left')
      grid.polygon(x=xp(c(lower,est,upper,est)),y=c(y,y+.018,y,y-.018),gp=gpar(fill='red3',col='red3'))
      txt(sprintf('%.3f',est),xs[5],y,8.5,TRUE)
      txt(sprintf('[%.3f; %.3f]',lower,upper),xs[6],y,8.5,TRUE)
      txt('100.0%',xs[6+j],y,8.5,TRUE)
    }
    txt(if(nrow(z)>=3) sprintf('Prediction interval: [%.3f; %.3f]',exp(mm$lower.predict),exp(mm$upper.predict)) else 'Prediction interval: not estimated (k < 3)',xs[1],.263,8.2,just='left',col='royalblue3')
    txt(sprintf('Heterogeneity: I2 = %.1f%%; tau2 = %.4f; Q = %.2f (P %s)',
                100*mm$I2,mm$tau2,mm$Q,pf(mm$pval.Q)),xs[1],.08,8,just='left')
  } else {
    txt('Single study: no pooled estimate',xs[1],.47,9,TRUE,'left')
    txt('Heterogeneity and prediction interval: not estimable',xs[1],.304,8.2,just='left',col='royalblue3')
  }
  grid.lines(x=c(pleft,pright),y=c(.23,.23))
  for(v in c(.25,.5,1,2,4,8,16)) {
    grid.lines(x=rep(xp(v),2),y=c(.23,.21))
    txt(format(v),xp(v),.176,8)
  }
  txt('HR per 10 ug/m3',.557,.123,8.7)
  txt(letter,.025,.036,12,TRUE,'left')
}
draw_subgroups <- function() {
  grid.newpage()
  pushViewport(viewport(layout=grid.layout(1,1)))
  for(i in seq_along(subsets)) {
    pushViewport(viewport(layout.pos.row=(i-1)%/%2+1,layout.pos.col=(i-1)%%2+1))
    panel(subsets[[i]],submodels[[i]],names(subsets)[i],LETTERS[i])
    popViewport()
  }
  popViewport()
}

for(nm in c('forest','funnel','egger','subgroups','leave_one_out')) {
  fun <- get(paste0('draw_',nm))
  wh <- switch(nm,forest=c(13,6),funnel=c(12,8),egger=c(12,8),subgroups=c(12,5.4),leave_one_out=c(13,6.5))
  svg(paste0(nm,'.svg'),width=wh[1],height=wh[2],family='sans',bg='white');fun();dev.off()
  png(file.path('previews',paste0(nm,'.png')),width=wh[1],height=wh[2],units='in',res=125,type='cairo');fun();dev.off()
}

model_row <- function(mm,group,model) {
  random <- model!='Fixed effect'
  data.frame(group=group,model=model,k=mm$k,
    HR=exp(if(random) mm$TE.random else mm$TE.common),
    lower=exp(if(random) mm$lower.random else mm$lower.common),
    upper=exp(if(random) mm$upper.random else mm$upper.common),
    p=if(random) mm$pval.random else mm$pval.common,
    Q=mm$Q,Q_df=mm$df.Q,Q_p=mm$pval.Q,I2_percent=100*mm$I2,tau2=mm$tau2)
}
results <- rbind(model_row(m,'All 6 articles','Random effects REML (Wald)'),
                 model_row(m,'All 6 articles','Fixed effect'),
                 model_row(m_hk,'All 6 articles','Random effects REML (modified HK)'),
                 model_row(m_index,'Exclude any-cancer-death S11/S45','Random effects REML (Wald)'),
                 model_row(m_strict,'Exclude S02/S11/S45: explicitly index-cancer-specific','Random effects REML (Wald)'),
                 model_row(m_linear,'Exclude nonlinear/large-scale extrapolation S13/S56','Random effects REML (Wald)'),
                 model_row(m_model_clear,'Exclude model-unclear S02','Random effects REML (Wald)'))
write.csv(results,'model_results.csv',row.names=FALSE)
write.csv(data.frame(HR=exp(m$TE.random),lower_prediction=exp(m$lower.predict),upper_prediction=exp(m$upper.predict)), 'prediction_interval.csv',row.names=FALSE)
sg_results <- do.call(rbind,lapply(seq_along(subsets),function(i) {
  z <- subsets[[i]]; mm <- submodels[[i]]; nm <- names(subsets)[i]
  if(is.null(mm)) return(data.frame(group=nm,model='Single study (not pooled)',k=1,
      HR=z$HR,lower=z$lower,upper=z$upper,p=NA,Q=NA,Q_df=NA,Q_p=NA,I2_percent=NA,tau2=NA))
  rbind(model_row(mm,nm,'Random effects REML (Wald)'),model_row(mm,nm,'Fixed effect'),
        model_row(submodels_hk[[i]],nm,'Random effects REML (modified HK)'))
}))
write.csv(sg_results,'subgroup_results.csv',row.names=FALSE)
write.csv(data.frame(cancer=target_titles,studies=vapply(target_cancers,function(x) sum(d$cancer==x),integer(1)),
                    displayed=target_titles %in% names(subsets)),'subgroup_eligibility.csv',row.names=FALSE)
write.csv(sd,'subgroup_input.csv',row.names=FALSE,fileEncoding='UTF-8')
write.csv(data.frame(test=c('Egger intercept t test','Begg rank correlation'),k=6,
    estimate=c(eg[1],begg$tau),statistic=c(eg[3],NA),df=c(4,NA),p=c(eg[4],begg$pval),
    lower=c(eg_ci[1],NA),upper=c(eg_ci[2],NA)),'bias_tests.csv',row.names=FALSE)
write.csv(data.frame(test='Between-cancer subgroup difference',k=nrow(sd),p=NA,reason='Not estimable: only Breast Cancer subgroup available'),'subgroup_difference_test.csv',row.names=FALSE)

d$weight_fixed_percent <- 100*m$w.common/sum(m$w.common)
d$weight_random_percent <- 100*m$w.random/sum(m$w.random)
write.csv(d,'analysis_input_with_weights.csv',row.names=FALSE,fileEncoding='UTF-8')
write.csv(loo,'leave_one_out.csv',row.names=FALSE)
saveRDS(list(input=d,meta=m,modified_HK=m_hk,index_cancer=m_index,strict_index_cancer=m_strict,linear_only=m_linear,model_clear=m_model_clear,egger=egger_fit,begg=begg,
             submodels=submodels,submodels_HK=submodels_hk,subgroup_test=subgroup_test,
             leave_one_out=loo),'analysis_objects.rds')
capture.output(print(m),print(m_hk),summary(egger_fit),print(begg),print(sg_results),print(subgroup_test),
               file='statistical_output.txt')
capture.output(sessionInfo(),file='sessionInfo.txt')
writeLines(c(paste('Completed:',Sys.time()),paste('RSTUDIO:',Sys.getenv('RSTUDIO')),
             paste('RStudio API:',rstudioapi::isAvailable()),paste('PID:',Sys.getpid()),
             paste('Working directory:',getwd()),paste('Source MD5:',tools::md5sum('analysis.R'))),
           'execution_record.txt')
print(results);print(sg_results)
cat('\nAnalysis and all five SVG figures completed.\n')

# Statistical methods: REML random effects with Wald CIs for reference-style plots;
# modified Hartung-Knapp and declared selection sensitivities are separate results.
# Funnel/Egger/Begg assess small-study effects, not definitive publication bias.
# Possible SEER cohort overlap retained per user instruction; correlated
# sampling errors cannot be recovered from aggregate data. Subgroups are exploratory.
writeLines(c('https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-13',
 'https://wviechtb.github.io/metafor/reference/leave1out.html',
 'https://wviechtb.github.io/metafor/reference/rma.uni.html'), 'method_references.txt')
