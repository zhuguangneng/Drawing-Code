# Run with Source in RStudio, with this project as the working directory.
# Cancer-specific mortality is pooled using the original adjusted HRs and CIs.
# Approximate HR-to-RR conversions are preserved in the extraction workbook but
# are not mixed with HRs in this analysis.
if (.Platform$OS.type == "windows") Sys.setlocale("LC_CTYPE", "English_United States.utf8")
library(meta)
library(metafor)

d <- read.csv("included_CSM_HR.csv", fileEncoding = "UTF-8-BOM", check.names = FALSE)
stopifnot(
  nrow(d) == 5L,
  setequal(d$effect_id, c("F046_2", "F084_PC_Full", "F149_1", "F149_3", "F150_4")),
  all(d$lower > 0 & d$lower <= d$HR & d$HR < d$upper),
  !anyDuplicated(d$cohort),
  length(unique(d$publication)) == 4L
)

d$study <- c(
  "Jiang 2023",
  "Korn 2025",
  "Smartt 2019 (bone sarcoma)",
  "Smartt 2019 (soft-tissue sarcoma)",
  "Masoud 2024"
)
d$point_label <- paste0(d$study, "\nHR = ", format(d$HR, trim = TRUE, scientific = FALSE))
d$logHR <- log(d$HR)
d$SE <- (log(d$upper) - log(d$lower)) / (2 * qnorm(.975))
d$original_CI <- sprintf("%.3f [%.3f; %.3f]", d$HR, d$lower, d$upper)

m <- metagen(
  TE = logHR, seTE = SE, studlab = study, data = d, sm = "HR",
  common = TRUE, random = TRUE, method.tau = "REML",
  method.random.ci = "classic", prediction = TRUE, method.predict = "HTS"
)

# Egger regression is exploratory because only five effect estimates are available.
egger_fit <- lm(I(logHR / SE) ~ I(1 / SE), data = d)
eg <- coef(summary(egger_fit))[1, ]
eg_df <- nrow(d) - 2L
eg_check <- regtest(d$logHR, sei = d$SE, model = "lm", predictor = "sei")
stopifnot(isTRUE(all.equal(unname(eg[4]), eg_check$pval, tolerance = 1e-8)))

pf <- function(x) {
  ifelse(x < .001, "< 0.001", paste0("= ", formatC(x, format = "f", digits = 3)))
}

draw_forest <- function() {
  # Published study CIs are displayed exactly; pooled CIs use reconstructed SEs.
  m_plot <- m
  m_plot$lower <- log(d$lower)
  m_plot$upper <- log(d$upper)
  forest(
    m_plot,
    leftcols = c("studlab", "TE", "seTE"),
    leftlabs = c("Study", "logHR", "SE(logHR)"),
    rightcols = c("effect", "ci", "w.common", "w.random"),
    rightlabs = c("HR", "95% CI", "Weight\n(fixed)", "Weight\n(random)"),
    text.common = "Fixed effect",
    text.random = "Random effects (REML)",
    xlab = "Hazard ratio (worse vs better access)",
    smlab = "Cancer-specific mortality",
    col.square = "grey65", col.square.lines = "grey30",
    col.diamond.common = "black", col.diamond.random = "firebrick3",
    col.predict = "royalblue3",
    print.I2 = TRUE, print.tau2 = TRUE, print.Q = TRUE, print.pval.Q = TRUE,
    test.overall.common = TRUE, test.overall.random = TRUE,
    prediction = TRUE, fontsize = 9.5, digits = 3, digits.se = 4,
    digits.tau2 = 4,
    label.left = "Lower mortality hazard",
    label.right = "Higher mortality hazard",
    addrows.below.overall = 5,
    xlim = c(.35, 4.5), at = c(.5, .75, 1, 1.5, 2, 3, 4)
  )
}

draw_funnel <- function() {
  op <- par(mar = c(5, 5, 5, 2), family = "sans")
  on.exit(par(op))
  ymax <- max(d$SE) * 1.22
  center <- m$TE.common
  lim <- range(c(d$logHR, center + c(-1, 1) * qnorm(.975) * ymax))
  plot(
    NA, xlim = lim, ylim = c(ymax, 0),
    xlab = "Hazard ratio (logarithmic scale)",
    ylab = "Standard error of log(HR)", xaxt = "n",
    main = "Funnel plot: cancer-specific mortality HR analysis"
  )
  ticks <- c(.5, .75, 1, 1.5, 2, 3)
  axis(1, at = log(ticks), labels = ticks)
  polygon(
    c(center, center - qnorm(.975) * ymax, center + qnorm(.975) * ymax),
    c(0, ymax, ymax), col = "grey94", border = NA
  )
  abline(v = center, lty = 2, col = "firebrick3")
  lines(center - qnorm(.975) * c(0, ymax), c(0, ymax), lty = 3)
  lines(center + qnorm(.975) * c(0, ymax), c(0, ymax), lty = 3)
  points(d$logHR, d$SE, pch = 21, bg = "grey65", cex = 1.3)
  # Manual label anchors prevent the two Smartt/Jiang labels from overlapping.
  lab_x <- d$logHR + c(.045, -.045, .045, -.045, .045)
  lab_y <- d$SE + c(.035, 0, -.028, 0, 0)
  lab_adj <- c(0, 1, 0, 1, 0)
  for (i in seq_len(nrow(d))) {
    segments(d$logHR[i], d$SE[i], lab_x[i], lab_y[i], col = "grey70", lwd = .7)
    text(lab_x[i], lab_y[i], labels = d$point_label[i],
         adj = c(lab_adj[i], .5), cex = .72)
  }
  mtext(
    paste0("Egger intercept test: P ", pf(eg[4]), " (df = ", eg_df, ")"),
    side = 3, line = .5
  )
  mtext(
    "Exploratory only: five effects from four publications; very low power for asymmetry",
    side = 1, line = 3.6, cex = .82
  )
  legend(
    "bottomleft",
    legend = c("Fixed-effect centre", "Pseudo 95% confidence limits"),
    lty = c(2, 3), col = c("firebrick3", "black"), bty = "n", cex = .82
  )
}

draw_egger <- function() {
  op <- par(mar = c(5, 5, 5, 2), family = "sans")
  on.exit(par(op))
  prec <- 1 / d$SE
  snd <- d$logHR / d$SE
  plot(
    prec, snd, xlim = c(0, max(prec) * 1.10),
    ylim = range(c(0, snd, eg[1])) + c(-1.3, 1.3),
    pch = 21, bg = "grey65", cex = 1.3,
    xlab = "Precision: 1 / SE(log HR)",
    ylab = "Standard normal deviate: log HR / SE",
    main = "Egger regression: cancer-specific mortality HR analysis"
  )
  abline(egger_fit, col = "firebrick3", lwd = 2)
  abline(h = 0, lty = 3, col = "grey60")
  # Manual anchors keep the two low-precision labels and the two HR=1.30 labels separate.
  lab_x <- c(9.0, 38.0, 11.5, 11.5, 3.4)
  lab_y <- c(2.15, -3.95, 3.05, 1.25, .82)
  lab_adj <- c(0, 1, 0, 0, 0)
  for (i in seq_len(nrow(d))) {
    segments(prec[i], snd[i], lab_x[i], lab_y[i], col = "grey70", lwd = .7)
    text(lab_x[i], lab_y[i], labels = d$point_label[i],
         adj = c(lab_adj[i], .5), cex = .72)
  }
  mtext(
    sprintf(
      "Intercept = %.3f; t = %.3f; df = %d; P %s",
      eg[1], eg[3], eg_df, pf(eg[4])
    ),
    side = 3, line = .5
  )
  mtext(
    "Exploratory only: five effects from four publications; asymmetry is not proof of publication bias",
    side = 1, line = 3.6, cex = .78
  )
}

for (nm in c("forest", "funnel", "egger")) {
  fun <- get(paste0("draw_", nm))
  w <- if (nm == "forest") 15 else 9
  h <- if (nm == "forest") 7.5 else 6.5
  svg(paste0(nm, ".svg"), width = w, height = h, family = "sans")
  fun()
  dev.off()
  png(
    paste0(nm, "_preview.png"), width = w, height = h,
    units = "in", res = 150, type = "cairo"
  )
  fun()
  dev.off()
}

d$weight_fixed_percent <- 100 * m$w.common / sum(m$w.common)
d$weight_random_percent <- 100 * m$w.random / sum(m$w.random)
write.csv(d, "analysis_input_with_weights.csv", row.names = FALSE, fileEncoding = "UTF-8")

results <- data.frame(
  model = c("Fixed effect", "Random effects REML"),
  k_effects = m$k,
  publications = length(unique(d$publication)),
  HR = exp(c(m$TE.common, m$TE.random)),
  lower = exp(c(m$lower.common, m$lower.random)),
  upper = exp(c(m$upper.common, m$upper.random)),
  p = c(m$pval.common, m$pval.random),
  Q = m$Q, Q_df = m$df.Q, Q_p = m$pval.Q,
  I2_percent = 100 * m$I2, tau2 = m$tau2,
  prediction_lower = c(NA, exp(m$lower.predict)),
  prediction_upper = c(NA, exp(m$upper.predict)),
  Egger_intercept = eg[1], Egger_t = eg[3],
  Egger_df = eg_df, Egger_p = eg[4]
)
write.csv(results, "model_results.csv", row.names = FALSE)
saveRDS(list(input = d, meta = m, egger = egger_fit), "analysis_objects.rds")
capture.output(print(m), summary(egger_fit), file = "statistical_output.txt")
capture.output(sessionInfo(), file = "sessionInfo.txt")
writeLines(
  c(
    paste("Completed:", Sys.time()),
    paste("RSTUDIO:", Sys.getenv("RSTUDIO")),
    paste("RStudio API:", rstudioapi::isAvailable()),
    paste("PID:", Sys.getpid()),
    paste("Working directory:", getwd())
  ),
  "execution_record.txt"
)
print(results)

# Small-sample and publication-level sensitivity analyses.
m_hk <- metagen(
  TE = logHR, seTE = SE, studlab = study, data = d, sm = "HR",
  common = TRUE, random = TRUE, method.tau = "REML",
  method.random.ci = "HK", prediction = FALSE
)

combine_publication <- function(x) {
  w <- 1 / x$SE^2
  data.frame(
    publication = x$publication[1],
    study = x$publication[1],
    effects_combined = nrow(x),
    logHR = sum(w * x$logHR) / sum(w),
    SE = sqrt(1 / sum(w))
  )
}
d_pub <- do.call(rbind, lapply(split(d, d$publication), combine_publication))
d_pub$HR <- exp(d_pub$logHR)
d_pub$lower <- exp(d_pub$logHR - qnorm(.975) * d_pub$SE)
d_pub$upper <- exp(d_pub$logHR + qnorm(.975) * d_pub$SE)
write.csv(d_pub, "publication_level_input.csv", row.names = FALSE)

m_pub <- metagen(
  TE = logHR, seTE = SE, studlab = study, data = d_pub, sm = "HR",
  common = TRUE, random = TRUE, method.tau = "REML",
  method.random.ci = "classic", prediction = FALSE
)
m_pub_hk <- metagen(
  TE = logHR, seTE = SE, studlab = study, data = d_pub, sm = "HR",
  common = TRUE, random = TRUE, method.tau = "REML",
  method.random.ci = "HK", prediction = FALSE
)
egger_pub_fit <- lm(I(logHR / SE) ~ I(1 / SE), data = d_pub)
egger_pub <- coef(summary(egger_pub_fit))[1, ]

# Full-text main analysis uses HR 1.10 for F149_3. The abstract reports 1.20
# with the same CI and P value, so the alternate report is tested separately.
d_alt <- d
d_alt$HR[d_alt$effect_id == "F149_3"] <- 1.20
d_alt$logHR <- log(d_alt$HR)
m_alt <- metagen(
  TE = logHR, seTE = SE, studlab = study, data = d_alt, sm = "HR",
  common = TRUE, random = TRUE, method.tau = "REML",
  method.random.ci = "classic", prediction = FALSE
)
egger_alt_fit <- lm(I(logHR / SE) ~ I(1 / SE), data = d_alt)
egger_alt <- coef(summary(egger_alt_fit))[1, ]

sensitivity <- data.frame(
  analysis = c(
    "Five effects: REML classic (main)",
    "Five effects: REML Hartung-Knapp",
    "Four publications: Smartt cohorts pre-combined, REML classic",
    "Four publications: Smartt cohorts pre-combined, REML Hartung-Knapp",
    "F149_3 alternate abstract HR 1.20, REML classic"
  ),
  effects = c(5, 5, 4, 4, 5),
  publications = c(4, 4, 4, 4, 4),
  HR = exp(c(m$TE.random, m_hk$TE.random, m_pub$TE.random,
             m_pub_hk$TE.random, m_alt$TE.random)),
  lower = exp(c(m$lower.random, m_hk$lower.random, m_pub$lower.random,
                m_pub_hk$lower.random, m_alt$lower.random)),
  upper = exp(c(m$upper.random, m_hk$upper.random, m_pub$upper.random,
                m_pub_hk$upper.random, m_alt$upper.random)),
  p = c(m$pval.random, m_hk$pval.random, m_pub$pval.random,
        m_pub_hk$pval.random, m_alt$pval.random),
  I2_percent = c(100 * m$I2, 100 * m_hk$I2, 100 * m_pub$I2,
                 100 * m_pub_hk$I2, 100 * m_alt$I2),
  tau2 = c(m$tau2, m_hk$tau2, m_pub$tau2, m_pub_hk$tau2, m_alt$tau2),
  Egger_p = c(eg[4], eg[4], egger_pub[4], egger_pub[4], egger_alt[4])
)
write.csv(sensitivity, "sensitivity_results.csv", row.names = FALSE)

# Leave-one-effect-out analysis, matching the layout used in the earlier meta-analysis.
loo_effect <- do.call(rbind, lapply(seq_len(nrow(d)), function(i) {
  x <- d[-i, , drop = FALSE]
  fit <- metagen(
    TE = logHR, seTE = SE, studlab = study, data = x, sm = "HR",
    common = TRUE, random = TRUE, method.tau = "REML",
    method.random.ci = "classic", prediction = FALSE
  )
  data.frame(
    omitted_effect_id = d$effect_id[i],
    omitted_effect = d$study[i],
    effects_remaining = fit$k,
    publications_remaining = length(unique(x$publication)),
    model = "Random effects REML",
    HR = unname(exp(fit$TE.random)),
    lower = unname(exp(fit$lower.random)),
    upper = unname(exp(fit$upper.random)),
    p = unname(fit$pval.random),
    I2_percent = unname(100 * fit$I2),
    tau2 = unname(fit$tau2),
    Q = unname(fit$Q), Q_p = unname(fit$pval.Q)
  )
}))
stopifnot(
  nrow(loo_effect) == 5L,
  all(loo_effect$effects_remaining == 4L),
  setequal(loo_effect$omitted_effect_id, d$effect_id),
  all(loo_effect$lower < loo_effect$HR & loo_effect$HR < loo_effect$upper)
)
write.csv(loo_effect, "leave_one_out_results.csv", row.names = FALSE)

draw_leave_one_out <- function() {
  op <- par(mar = c(5.7, 2.5, 4.2, 1.5), family = "sans", xpd = NA)
  on.exit(par(op))
  plot(
    NA, xlim = log(c(.38, 4.5)), ylim = c(.35, 7.25), axes = FALSE,
    xlab = "", ylab = "", main = "Leave-one-effect-out sensitivity analysis"
  )
  abline(h = c(5.48, .55), col = "grey85")
  segments(log(.65), .65, log(.65), 6.55, col = "grey80")
  segments(log(1.7), .65, log(1.7), 6.55, col = "grey80")
  segments(0, .65, 0, 6.55, col = "grey65", lty = 2)
  segments(log(exp(m$TE.random)), .65, log(exp(m$TE.random)), 6.55,
           col = "firebrick3", lty = 3)
  text(log(.40), 6.82, "Analysis", adj = 0, font = 2, cex = .98)
  text(log(.84), 6.82, "Pooled HR", adj = 0, font = 2, cex = .98)
  text(log(1.82), 6.82, "HR (95% CI)", adj = 0, font = 2, cex = .98)
  text(log(3.15), 6.82, expression(I^2), adj = .5, font = 2, cex = .98)
  text(log(4.02), 6.82, "P", adj = .5, font = 2, cex = .98)
  yy <- 6:1
  vals <- c(exp(m$TE.random), loo_effect$HR)
  lows <- c(exp(m$lower.random), loo_effect$lower)
  highs <- c(exp(m$upper.random), loo_effect$upper)
  labels <- c("All 5 effects (4 publications)", paste0("Omit ", loo_effect$omitted_effect))
  pvals <- c(m$pval.random, loo_effect$p)
  i2 <- c(100 * m$I2, loo_effect$I2_percent)
  for (j in seq_along(yy)) {
    col <- if (j == 1L) "firebrick3" else "grey25"
    segments(log(lows[j]), yy[j], log(highs[j]), yy[j], lwd = 2, col = col)
    segments(log(lows[j]), yy[j] - .08, log(lows[j]), yy[j] + .08, col = col)
    segments(log(highs[j]), yy[j] - .08, log(highs[j]), yy[j] + .08, col = col)
    points(log(vals[j]), yy[j], pch = if (j == 1L) 18 else 15,
           cex = if (j == 1L) 1.5 else 1.2, col = col)
    text(log(.40), yy[j], labels[j], adj = 0, cex = .84,
         font = if (j == 1L) 2 else 1)
    text(log(1.82), yy[j], sprintf("%.3f (%.3f-%.3f)", vals[j], lows[j], highs[j]),
         adj = 0, cex = .80, font = if (j == 1L) 2 else 1)
    text(log(3.15), yy[j], sprintf("%.1f%%", i2[j]), cex = .82)
    text(log(4.02), yy[j], ifelse(pvals[j] < .001, "<.001", sprintf("%.3f", pvals[j])),
         cex = .82)
  }
  axis(1, at = log(c(.6, .8, 1, 1.2, 1.4, 1.6)),
       labels = c(".6", ".8", "1.0", "1.2", "1.4", "1.6"), cex.axis = .9)
  mtext("Hazard ratio (random-effects REML)", side = 1, line = 2.5, cex = .95)
  mtext(expression("Each omission leaves 4 effects; " * I^2 *
                   " and P are recomputed for each model."),
        side = 1, line = 4, cex = .82)
}

svg("leave_one_out.svg", width = 13, height = 7, family = "sans")
draw_leave_one_out()
dev.off()
png("leave_one_out_preview.png", width = 13, height = 7,
    units = "in", res = 150, type = "cairo")
draw_leave_one_out()
dev.off()
capture.output(loo_effect, file = "leave_one_out_output.txt")
writeLines(c(paste("Leave-one-effect-out completed:", Sys.time()),
             paste("RSTUDIO:", Sys.getenv("RSTUDIO")),
             paste("RStudio API:", rstudioapi::isAvailable()),
             paste("PID:", Sys.getpid())), "leave_one_out_execution_record.txt")
print(loo_effect)

# Publication-level influence analysis. Smartt 2019 is removed as one publication,
# which simultaneously removes its two non-overlapping sarcoma cohorts.
pubs <- unique(d$publication)
loo_pub <- do.call(rbind, lapply(pubs, function(pub) {
  x <- d[d$publication != pub, , drop = FALSE]
  fit <- metagen(
    TE = logHR, seTE = SE, studlab = study, data = x, sm = "HR",
    common = TRUE, random = TRUE, method.tau = "REML",
    method.random.ci = "classic", prediction = FALSE
  )
  data.frame(
    omitted_publication = pub,
    omitted_effects = sum(d$publication == pub),
    effects_remaining = fit$k,
    publications_remaining = length(unique(x$publication)),
    model = "Random effects REML",
    HR = unname(exp(fit$TE.random)), lower = unname(exp(fit$lower.random)),
    upper = unname(exp(fit$upper.random)), p = unname(fit$pval.random),
    I2_percent = unname(100 * fit$I2), tau2 = unname(fit$tau2),
    Q = unname(fit$Q), Q_p = unname(fit$pval.Q)
  )
}))
stopifnot(nrow(loo_pub) == 4L, all(loo_pub$publications_remaining == 3L),
          setequal(loo_pub$omitted_publication, pubs),
          all(loo_pub$lower < loo_pub$HR & loo_pub$HR < loo_pub$upper))
write.csv(loo_pub, "leave_one_publication_out_results.csv", row.names = FALSE)

draw_leave_one_publication_out <- function() {
  op <- par(mar = c(5.7, 2.5, 4.2, 1.5), family = "sans", xpd = NA)
  on.exit(par(op))
  plot(NA, xlim = log(c(.38, 4.5)), ylim = c(.35, 6.25), axes = FALSE,
       xlab = "", ylab = "", main = "Leave-one-publication-out sensitivity analysis")
  abline(h = c(4.48, .55), col = "grey85")
  segments(log(.65), .65, log(.65), 5.55, col = "grey80")
  segments(log(1.7), .65, log(1.7), 5.55, col = "grey80")
  segments(0, .65, 0, 5.55, col = "grey65", lty = 2)
  segments(log(exp(m$TE.random)), .65, log(exp(m$TE.random)), 5.55,
           col = "firebrick3", lty = 3)
  text(log(.40), 5.82, "Analysis", adj = 0, font = 2, cex = .98)
  text(log(.84), 5.82, "Pooled HR", adj = 0, font = 2, cex = .98)
  text(log(1.82), 5.82, "HR (95% CI)", adj = 0, font = 2, cex = .98)
  text(log(3.15), 5.82, expression(I^2), adj = .5, font = 2, cex = .98)
  text(log(4.02), 5.82, "P", adj = .5, font = 2, cex = .98)
  yy <- 5:1
  vals <- c(exp(m$TE.random), loo_pub$HR)
  lows <- c(exp(m$lower.random), loo_pub$lower)
  highs <- c(exp(m$upper.random), loo_pub$upper)
  labels <- c("All 5 effects (4 publications)", paste0("Omit ", loo_pub$omitted_publication))
  pvals <- c(m$pval.random, loo_pub$p)
  i2 <- c(100 * m$I2, loo_pub$I2_percent)
  for (j in seq_along(yy)) {
    col <- if (j == 1L) "firebrick3" else "grey25"
    segments(log(lows[j]), yy[j], log(highs[j]), yy[j], lwd = 2, col = col)
    segments(log(lows[j]), yy[j] - .08, log(lows[j]), yy[j] + .08, col = col)
    segments(log(highs[j]), yy[j] - .08, log(highs[j]), yy[j] + .08, col = col)
    points(log(vals[j]), yy[j], pch = if (j == 1L) 18 else 15,
           cex = if (j == 1L) 1.5 else 1.2, col = col)
    text(log(.40), yy[j], labels[j], adj = 0, cex = .88,
         font = if (j == 1L) 2 else 1)
    text(log(1.82), yy[j], sprintf("%.3f (%.3f-%.3f)", vals[j], lows[j], highs[j]),
         adj = 0, cex = .82, font = if (j == 1L) 2 else 1)
    text(log(3.15), yy[j], sprintf("%.1f%%", i2[j]), cex = .84)
    text(log(4.02), yy[j], ifelse(pvals[j] < .001, "<.001", sprintf("%.3f", pvals[j])),
         cex = .84)
  }
  axis(1, at = log(c(.6, .8, 1, 1.2, 1.4, 1.6)),
       labels = c(".6", ".8", "1.0", "1.2", "1.4", "1.6"), cex.axis = .9)
  mtext("Hazard ratio (random-effects REML)", side = 1, line = 2.5, cex = .95)
  mtext(expression("Each omission removes one publication; " * I^2 *
                   " and P are recomputed for each model."),
        side = 1, line = 4, cex = .82)
}

svg("leave_one_publication_out.svg", width = 13, height = 6.3, family = "sans")
draw_leave_one_publication_out()
dev.off()
png("leave_one_publication_out_preview.png", width = 13, height = 6.3,
    units = "in", res = 150, type = "cairo")
draw_leave_one_publication_out()
dev.off()
capture.output(loo_pub, file = "leave_one_publication_out_output.txt")
writeLines(c(paste("Leave-one-publication-out completed:", Sys.time()),
             paste("RSTUDIO:", Sys.getenv("RSTUDIO")),
             paste("RStudio API:", rstudioapi::isAvailable()),
             paste("PID:", Sys.getpid())), "leave_one_publication_out_execution_record.txt")
print(loo_pub)
