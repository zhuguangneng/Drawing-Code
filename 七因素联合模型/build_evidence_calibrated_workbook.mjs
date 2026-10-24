import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
const runtimeRequire = createRequire("C:/Users/xc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/package.json");
const { FileBlob, SpreadsheetFile, Workbook } = runtimeRequire("@oai/artifact-tool");

const workspace = "C:/Users/xc/Documents/Codex/2026-10-13/wo";
const inputDir = path.join(workspace, "outputs/joint_effect_model_evidence_calibrated");
const outputPath = path.join(inputDir, "七因素综合效应蒙特卡洛结果_证据校准版.xlsx");
const previewDir = path.join(workspace, "work/joint_effect_model_evidence_calibrated/previews");

function parseCsv(text) {
  const rows = []; let row = []; let field = ""; let quoted = false;
  const clean = text.replace(/^\uFEFF/, "");
  for (let i = 0; i < clean.length; i++) {
    const ch = clean[i];
    if (quoted) {
      if (ch === '"' && clean[i + 1] === '"') { field += '"'; i++; }
      else if (ch === '"') quoted = false;
      else field += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") { row.push(field); field = ""; }
    else if (ch === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
    else if (ch !== "\r") field += ch;
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  const headers = rows[0];
  return rows.slice(1).filter(r => r.some(v => v !== "")).map(r =>
    Object.fromEntries(headers.map((h, i) => [h, r[i] ?? ""])));
}

const [results, config, validation, patternText, conditionalText, residualText] = await Promise.all([
  fs.readFile(path.join(inputDir, "analysis_results.json"), "utf8").then(JSON.parse),
  fs.readFile(path.join(inputDir, "analysis_config.json"), "utf8").then(JSON.parse),
  fs.readFile(path.join(inputDir, "validation_report.json"), "utf8").then(JSON.parse),
  fs.readFile(path.join(inputDir, "pattern_probabilities.csv"), "utf8"),
  fs.readFile(path.join(inputDir, "evidence_records/conditional_overlap_evidence.csv"), "utf8"),
  fs.readFile(path.join(inputDir, "evidence_records/diagnostic_residual_evidence.csv"), "utf8"),
]);
const patternRows = parseCsv(patternText);
const conditionalRows = parseCsv(conditionalText);
const residualRows = parseCsv(residualText);
const main = results.main;
const scenarios = results.scenarios;
const overlapRows = results.overlap_constraints;
const shapleyRows = results.shapley;

const wb = Workbook.create();
const summary = wb.worksheets.add("综合主结果");
const inputs = wb.worksheets.add("模型参数");
const overlap = wb.worksheets.add("重叠约束");
const patterns = wb.worksheets.add("64种组合");
const sensitivity = wb.worksheets.add("敏感性");
const allocation = wb.worksheets.add("联合增量分配");
const conditionalEvidence = wb.worksheets.add("条件概率证据");
const residualEvidence = wb.worksheets.add("D残余证据");
const diagnostics = wb.worksheets.add("运行诊断");

const navy = "#17365D", blue = "#2F75B5", teal = "#0F6B78";
const lightBlue = "#DDEBF7", paleGreen = "#E2F0D9", paleYellow = "#FFF2CC";
const paleRed = "#FCE4D6", white = "#FFFFFF", border = "#B4C6E7", dark = "#222222";
for (const sheet of [summary, inputs, overlap, patterns, sensitivity, allocation, conditionalEvidence, residualEvidence, diagnostics]) {
  sheet.showGridLines = false;
  sheet.getRange("A1:Q220").format.font = { name: "Arial", size: 10, color: dark };
  sheet.getRange("A1:Q220").format.verticalAlignment = "center";
}
summary.tabColor = navy; inputs.tabColor = blue; overlap.tabColor = "#5B9BD5";
conditionalEvidence.tabColor = "#ED7D31"; residualEvidence.tabColor = "#C55A11";
diagnostics.tabColor = "#A5A5A5";

function title(sheet, text, subtitle, end = "L") {
  sheet.getRange(`A2:${end}2`).format.borders = { bottom: { style: "medium", color: navy } };
  sheet.getRange("A2").values = [[text]];
  sheet.getRange("A2").format.font = { name: "Arial", size: 15, bold: true, color: navy };
  sheet.getRange("A3").values = [[subtitle]];
  sheet.getRange(`A3:${end}3`).format.font = { name: "Arial", size: 10, italic: true, color: "#666666" };
}
function header(range) {
  range.format.fill = navy;
  range.format.font = { name: "Arial", size: 10, bold: true, color: white };
  range.format.horizontalAlignment = "center";
  range.format.wrapText = true;
  range.format.borders = { preset: "all", style: "thin", color: white };
}
function body(range) {
  range.format.borders = { insideHorizontal: { style: "thin", color: "#D9E2F3" }, bottom: { style: "thin", color: border } };
}
function n(v) {
  if (v === "" || v === null || v === undefined) return "";
  const x = Number(v);
  return Number.isFinite(x) ? x : v;
}

// Summary
title(summary, "七因素综合效应蒙特卡洛结果（证据校准版）", "独立新建；旧版Excel、代码和Word均未覆盖；100,000次模拟", "L");
summary.getRange("A5:L5").values = [[
  "2023反事实基线", results.baseline_models[0].baseline_deaths_median,
  "综合死亡数", main.joint_deaths_median,
  "综合超额死亡", main.additional_deaths_median,
  "相对增加", main.percent_change_median / 100,
  "相对T单独新增", main.beyond_treatment_deaths_median,
  "校验状态", validation.status,
]];
for (const c of ["A5","C5","E5","G5","I5","K5"]) { summary.getRange(c).format.fill = lightBlue; summary.getRange(c).format.font = { bold: true, color: navy }; }
for (const c of ["B5","D5","F5","H5","J5","L5"]) { summary.getRange(c).format.fill = paleGreen; summary.getRange(c).format.font = { bold: true }; }
summary.getRange("B5:F5").format.numberFormat = "#,##0.0"; summary.getRange("H5").format.numberFormat = "0.0%"; summary.getRange("J5").format.numberFormat = "#,##0.0";
summary.getRange("A8:E8").values = [["主分析指标","中位数","95%UI下限","95%UI上限","单位"]]; header(summary.getRange("A8:E8"));
summary.getRange("A9:E13").values = [
  ["2023反事实登记癌症死亡基线", results.baseline_models[0].baseline_deaths_median, results.baseline_models[0].baseline_deaths_lower_2_5, results.baseline_models[0].baseline_deaths_upper_97_5, "例"],
  ["七因素联合情景死亡数", main.joint_deaths_median, main.joint_deaths_lower_2_5, main.joint_deaths_upper_97_5, "例"],
  ["七因素联合超额死亡", main.additional_deaths_median, main.additional_deaths_lower_2_5, main.additional_deaths_upper_97_5, "例"],
  ["相对基线增加", main.percent_change_median/100, main.percent_change_lower_2_5/100, main.percent_change_upper_97_5/100, ""],
  ["相对T单独新增死亡", main.beyond_treatment_deaths_median, main.beyond_treatment_deaths_lower_2_5, main.beyond_treatment_deaths_upper_97_5, "例"],
  ]; body(summary.getRange("A9:E13")); summary.getRange("B9:D11").format.numberFormat = "#,##0.0"; summary.getRange("B12:D12").format.numberFormat = "0.0%"; summary.getRange("B13:D13").format.numberFormat = "#,##0.0";
summary.getRange("H8:L8").values = [["关键模型决定","","","",""]]; header(summary.getRange("H8:L8"));
const summaryNotes = [
  ["条件关联", "P(T|A/D/H/C)=1.000/0.827/0.920/0.821；P与T独立。"],
  ["覆盖假设", "A/H/C与T并存时残余效应=0。"],
  ["D残余效应", "主分析κ=0.5，即HR_D^0.5；κ=0和1为结构敏感性。"],
  ["治疗效应", "T的HR来自总体生存/全因死亡，在癌症特异性模型中为外部代理。"],
  ["解释范围", "模型情景推演；95%UI不包含结构选择的不确定性。"],
];
summary.getRange("H9:I13").values = summaryNotes; summary.getRange("H9:H13").format.fill = paleYellow; summary.getRange("H9:H13").format.font = { bold:true, color:"#7F6000" }; summary.getRange("I9:I13").format.wrapText = true; body(summary.getRange("H9:I13"));
summary.freezePanes.freezeRows(5);
for (const [c,w] of Object.entries({A:32,B:16,C:18,D:16,E:14,F:14,G:12,H:18,I:62,J:14,K:14,L:14})) summary.getRange(`${c}1:${c}28`).format.columnWidth=w;
summary.getRange("A1:L28").format.rowHeight=23; summary.getRange("H9:I13").format.rowHeight=42;

// Inputs
title(inputs, "模型参数", "效应量和有效暴露份额；结果为程序快照，参数变化需重新运行", "O");
inputs.getRange("A5:O5").values = [["代码","因素","结局","Meta模型","HR","95%CI下限","95%CI上限","效应单位","f低","f主","f高","I²","Δx/周数","主有效HR","来源"]]; header(inputs.getRange("A5:O5"));
const factorRows = config.factor_inputs;
inputs.getRange(`A6:M${5+factorRows.length}`).values = factorRows.map(r=>[r.code,r.factor_zh,r.code==="T"?"总体生存/全因死亡代理":"癌症特异性死亡/生存",r.model==="random"?"随机效应":"固定效应",r.hr,r.lower,r.upper,r.effect_type==="per10"?"每10 µg/m³":r.code==="T"?"每4周":"直接HR",r.f_low,r.f_main,r.f_high,r.i2??"",r.code==="E"?r.delta_x_main:r.code==="T"?12:""]);
for(let i=0;i<factorRows.length;i++){const rr=6+i,code=factorRows[i].code;inputs.getRange(`N${rr}`).formulas=[[code==="E"?`=E${rr}^(M${rr}/10)`:code==="T"?`=E${rr}^(M${rr}/4)`: `=E${rr}`]];inputs.getRange(`O${rr}`).values=[[code==="T"?"原文总体生存/全因死亡HR":"现行癌症特异性Meta结果"]];}
body(inputs.getRange(`A6:O${5+factorRows.length}`)); inputs.getRange(`E6:G${5+factorRows.length}`).format.numberFormat="0.000"; inputs.getRange(`I6:K${5+factorRows.length}`).format.numberFormat="0%"; inputs.getRange(`M6:N${5+factorRows.length}`).format.numberFormat="0.000"; inputs.getRange(`A${5+factorRows.length}:O${5+factorRows.length}`).format.fill=paleYellow;
inputs.freezePanes.freezeRows(5); for(const [c,w] of Object.entries({A:9,B:30,C:25,D:12,E:11,F:11,G:11,H:17,I:9,J:9,K:9,L:9,M:12,N:14,O:34})) inputs.getRange(`${c}1:${c}24`).format.columnWidth=w; inputs.getRange("A6:O12").format.rowHeight=38;

// Overlap
title(overlap, "证据校准的条件关联", "OR在固定有效边际下求合法2×2交集；A主分析嵌套于T；P与T独立", "N");
overlap.getRange("A5:H5").values=[["因素对","证据基础","规则/参数","fi","fT","目标交集","P(T|i)","效应路径"]]; header(overlap.getRange("A5:H5"));
const primaryOverlap=overlapRows.filter(r=>r.overlap_scenario_key==="evidence_primary");
const basis={"A-T":"实际许可延迟/拒绝：定义性嵌套","D-T":"Gade 2×2 OR=4.4299","H-T":"RCR 60中心放疗延迟92%","C-T":"Tamirat调整OR=2.54"};
overlap.getRange("A6:H9").values=primaryOverlap.map(r=>[r.factor_pair,basis[r.factor_pair],r.rule==="nested"?"嵌套":`OR=${Number(r.association_parameter).toFixed(4)}`,r.f_i,r.f_T,r.target_intersection,r.p_T_given_i,r.factor_pair==="D-T"?"并存时D保留50%对数HR":"并存时残余效应=0"]); body(overlap.getRange("A6:H9")); overlap.getRange("D6:G9").format.numberFormat="0.0000"; overlap.getRange("A6:H9").format.rowHeight=38; overlap.getRange("A6:H9").format.wrapText=true;
overlap.getRange("A12:N12").values=[["情景键","情景","因素对","规则","OR/参数","fi","fT","Fréchet下限","Fréchet上限","独立交集","目标交集","P(T|i)","P(i|T)","用途"]]; header(overlap.getRange("A12:N12"));
overlap.getRange(`A13:N${12+overlapRows.length}`).values=overlapRows.map(r=>[r.overlap_scenario_key,r.overlap_scenario,r.factor_pair,r.rule,n(r.association_parameter),n(r.f_i),n(r.f_T),n(r.frechet_lower),n(r.frechet_upper),n(r.independent_intersection),n(r.target_intersection),n(r.p_T_given_i),n(r.p_i_given_T),r.use]); body(overlap.getRange(`A13:N${12+overlapRows.length}`)); overlap.getRange(`E13:M${12+overlapRows.length}`).format.numberFormat="0.0000";
for(let i=0;i<overlapRows.length;i++) if(overlapRows[i].overlap_scenario_key==="evidence_primary") overlap.getRange(`A${13+i}:N${13+i}`).format.fill=paleGreen;
overlap.freezePanes.freezeRows(12); for(const [c,w] of Object.entries({A:21,B:25,C:10,D:11,E:12,F:9,G:9,H:14,I:14,J:14,K:14,L:14,M:14,N:26})) overlap.getRange(`${c}1:${c}${14+overlapRows.length}`).format.columnWidth=w;

// Patterns
title(patterns,"64种互斥联合暴露组合","二元顺序A、D、H、P、C、T；主效应结构为A/H/C覆盖、D κ=0.5","L");
const byPattern=new Map();
for(const r of patternRows){if(!byPattern.has(r.pattern))byPattern.set(r.pattern,{bits:r});const t=byPattern.get(r.pattern);if(r.overlap_scenario_key==="independent")t.pi=n(r.probability);if(r.overlap_scenario_key==="evidence_primary"){t.pp=n(r.probability);t.rr=n(r.point_rr);t.weight=n(r.weighted_point_rr);}if(r.overlap_scenario_key==="evidence_high")t.ph=n(r.probability);}
const patternMatrix=[...byPattern.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(([id,r])=>[`P-${id}`,n(r.bits.A),n(r.bits.D),n(r.bits.H),n(r.bits.P),n(r.bits.C),n(r.bits.T),r.pi,r.pp,r.ph,r.rr,r.weight]);
patterns.getRange("A5:L5").values=[["组合ID","A","D","H","P","C","T","独立概率","主值概率","高值概率","路径调整RR","主值加权RR"]]; header(patterns.getRange("A5:L5")); patterns.getRange(`A6:L${5+patternMatrix.length}`).values=patternMatrix; body(patterns.getRange(`A6:L${5+patternMatrix.length}`));
const totalRow=6+patternMatrix.length;patterns.getRange(`A${totalRow}:G${totalRow}`).values=[["合计","","","","","",""]];patterns.getRange(`H${totalRow}:L${totalRow}`).formulas=[[`=SUM(H6:H${totalRow-1})`,`=SUM(I6:I${totalRow-1})`,`=SUM(J6:J${totalRow-1})`,"",`=SUM(L6:L${totalRow-1})`]];patterns.getRange(`A${totalRow}:L${totalRow}`).format.fill=lightBlue;patterns.getRange(`H6:J${totalRow}`).format.numberFormat="0.000000";patterns.getRange(`K6:L${totalRow}`).format.numberFormat="0.0000";patterns.freezePanes.freezeRows(5);
for(const [c,w] of Object.entries({A:12,B:7,C:7,D:7,E:7,F:7,G:7,H:14,I:14,J:14,K:16,L:16}))patterns.getRange(`${c}1:${c}${totalRow}`).format.columnWidth=w;

// Sensitivity
title(sensitivity,"结构与参数敏感性分析","每行独立运行；结构选择未混入同一个95%UI","L");
sensitivity.getRange("A5:L5").values=[["类别","情景","效应结构","重叠情景","g","综合死亡中位数","超额死亡中位数","95%UI下限","95%UI上限","相对增加","相对T新增","说明"]];header(sensitivity.getRange("A5:L5"));
const sens=scenarios.filter(r=>r.category!=="main");
const cat={effect_structure:"效应结构",overlap:"暴露重叠",exposure_fraction:"暴露比例",factor_fraction_oat:"单因素f（OAT）",communication_legacy_definition:"C旧定义（含Fair）",transportability:"迁移系数",particulate_delta:"颗粒物浓度（探索性）",meta_model:"Meta模型",treatment_endpoint:"治疗结局代理",baseline_model:"基线模型"};
const struct={evidence_calibrated:"A/H/C覆盖；D κ=0.5",diagnosis_residual_0:"A/H/C覆盖；D κ=0",diagnosis_residual_1:"A/H/C覆盖；D κ=1",full_product:"完全乘法",additive:"加性超额风险"};
function noteZh(note) {
  return String(note ?? "")
    .replaceAll("primary proxy", "主分析完整代理迁移")
    .replaceAll("endpoint transfer sensitivity", "结局迁移敏感性")
    .replaceAll("T overlap retained", "保留T的重叠结构")
    .replaceAll("reproduction", "原文数值复现")
    .replaceAll("original time sensitivity", "原文时间敏感性");
}
sensitivity.getRange(`A6:L${5+sens.length}`).values=sens.map(r=>[cat[r.category]??r.category,r.scenario,struct[r.structure]??r.structure,r.overlap_scenario,n(r.g),n(r.joint_deaths_median),n(r.additional_deaths_median),n(r.additional_deaths_lower_2_5),n(r.additional_deaths_upper_97_5),n(r.percent_change_median)/100,n(r.beyond_treatment_deaths_median),noteZh(r.notes)]);body(sensitivity.getRange(`A6:L${5+sens.length}`));sensitivity.getRange(`E6:E${5+sens.length}`).format.numberFormat="0.00";sensitivity.getRange(`F6:I${5+sens.length}`).format.numberFormat="#,##0.0";sensitivity.getRange(`J6:J${5+sens.length}`).format.numberFormat="0.0%";sensitivity.getRange(`K6:K${5+sens.length}`).format.numberFormat="#,##0.0";sensitivity.getRange(`A6:L${5+sens.length}`).format.wrapText=true;sensitivity.freezePanes.freezeRows(5);
for(const [c,w] of Object.entries({A:18,B:36,C:24,D:24,E:8,F:16,G:17,H:14,I:14,J:13,K:15,L:34}))sensitivity.getRange(`${c}1:${c}${6+sens.length}`).format.columnWidth=w;

// Shapley
title(allocation,"七因素联合模型增量分配","精确遍历2⁷子集；逐轮分配和等于联合增量","K");allocation.getRange("A5:K5").values=[["代码","因素","结局","分配中位数","95%UI下限","95%UI上限","占比中位数","占比下限","占比上限","P(>0)","解释"]];header(allocation.getRange("A5:K5"));allocation.getRange(`A6:K${5+shapleyRows.length}`).values=shapleyRows.map(r=>[r.code,r.factor_zh,r.code==="T"?"总体生存/全因死亡代理":"癌症特异性死亡/生存",r.contribution_median,r.contribution_lower_2_5,r.contribution_upper_97_5,r.share_percent_median/100,r.share_percent_lower_2_5/100,r.share_percent_upper_97_5/100,r.p_contribution_positive_percent/100,r.interpretation]);body(allocation.getRange(`A6:K${5+shapleyRows.length}`));allocation.getRange(`D6:F${5+shapleyRows.length}`).format.numberFormat="#,##0.0";allocation.getRange(`G6:J${5+shapleyRows.length}`).format.numberFormat="0.0%";allocation.getRange(`A6:K${5+shapleyRows.length}`).format.wrapText=true;for(const [c,w] of Object.entries({A:9,B:30,C:25,D:14,E:14,F:14,G:14,H:14,I:14,J:12,K:36}))allocation.getRange(`${c}1:${c}20`).format.columnWidth=w;

// Conditional evidence
title(conditionalEvidence,"条件概率证据记录","直接资料、代理资料、边际校准和模型决策分列记录","Q");
const ceHeaders=["因素对","研究/资料","证据类别","样本量","原始观察","原始统计量","关联指标","关联值","95%CI下限","95%CI上限","fi","fT","模型P(T|i)","模型低值","模型高值","用途","局限性","URL"];
conditionalEvidence.getRange("A5:R5").values=[ceHeaders];header(conditionalEvidence.getRange("A5:R5"));conditionalEvidence.getRange(`A6:R${5+conditionalRows.length}`).values=conditionalRows.map(r=>[r.factor_pair,r.citation,r.evidence_class,n(r.population_n),r.source_observation,r.raw_statistic,r.association_measure,n(r.association_value),n(r.association_lower_95),n(r.association_upper_95),n(r.model_f_i),n(r.model_f_T),n(r.model_P_T_given_i),n(r.model_P_low),n(r.model_P_high),r.model_use,r.limitation,r.url]);body(conditionalEvidence.getRange(`A6:R${5+conditionalRows.length}`));conditionalEvidence.getRange(`H6:O${5+conditionalRows.length}`).format.numberFormat="0.0000";conditionalEvidence.getRange(`A6:R${5+conditionalRows.length}`).format.wrapText=true;conditionalEvidence.getRange(`A6:R${5+conditionalRows.length}`).format.rowHeight=64;conditionalEvidence.freezePanes.freezeRows(5);
for(const [c,w] of Object.entries({A:9,B:30,C:23,D:12,E:38,F:28,G:19,H:13,I:13,J:13,K:9,L:9,M:15,N:14,O:14,P:34,Q:40,R:48}))conditionalEvidence.getRange(`${c}1:${c}${6+conditionalRows.length}`).format.columnWidth=w;

// D residual evidence
title(residualEvidence,"诊断延迟残余效应证据","未找到直接中介比例；κ=0.5是中心预设，κ=0与1为结构敏感性","F");residualEvidence.getRange("A5:F5").values=[["证据","证据类别","发现","含义","对κ的支持","URL或本地路径"]];header(residualEvidence.getRange("A5:F5"));residualEvidence.getRange(`A6:F${5+residualRows.length}`).values=residualRows.map(r=>[r.evidence,r.evidence_class,r.finding,r.implication,r.supports_kappa,r.url_or_path]);body(residualEvidence.getRange(`A6:F${5+residualRows.length}`));residualEvidence.getRange(`A6:F${5+residualRows.length}`).format.wrapText=true;residualEvidence.getRange(`A6:F${5+residualRows.length}`).format.rowHeight=82;residualEvidence.freezePanes.freezeRows(5);for(const [c,w] of Object.entries({A:30,B:25,C:52,D:52,E:42,F:58}))residualEvidence.getRange(`${c}1:${c}${6+residualRows.length}`).format.columnWidth=w;

// Diagnostics
title(diagnostics,"运行诊断与复现记录","概率、边际、交集、Shapley逐轮加总及公式错误检查","H");diagnostics.getRange("A5:C5").values=[["检查","结果","判定"]];header(diagnostics.getRange("A5:C5"));
const checks=[
  ["64组合概率和",validation.pattern_probability_sum,Math.abs(validation.pattern_probability_sum-1)<1e-12?"通过":"失败"],
  ["最小组合概率",validation.minimum_pattern_probability,validation.minimum_pattern_probability>=0?"通过":"失败"],
  ["最大边际误差",validation.max_abs_marginal_error,validation.max_abs_marginal_error<1e-12?"通过":"失败"],
  ["最大交集误差",validation.max_abs_pair_error,validation.max_abs_pair_error<1e-12?"通过":"失败"],
  ["全部情景约束最大误差",validation.all_reported_scenarios_constraint_max_abs_error,validation.all_reported_scenarios_constraint_max_abs_error<1e-12?"通过":"失败"],
  ["T单独公式退化误差",validation.treatment_only_reduction_max_abs_error,validation.treatment_only_reduction_max_abs_error<1e-12?"通过":"失败"],
  ["全HR=1恒等误差",validation.neutral_effect_max_abs_error,validation.neutral_effect_max_abs_error<1e-12?"通过":"失败"],
  ["固定分布全联盟误差",validation.fixed_distribution_full_coalition_max_abs_error,validation.fixed_distribution_full_coalition_max_abs_error<1e-12?"通过":"失败"],
  ["Shapley逐轮加总最大误差",validation.shapley_additivity_max_abs_error,validation.shapley_additivity_max_abs_error<1e-9?"通过":"失败"],
  ["权威基线摘要最大误差",validation.authoritative_baseline_summary_max_abs_error,validation.authoritative_baseline_summary_max_abs_error<1e-12?"通过":"失败"],
  ["总状态",validation.status,validation.status==="PASS"?"通过":"失败"],
];diagnostics.getRange(`A6:C${5+checks.length}`).values=checks;body(diagnostics.getRange(`A6:C${5+checks.length}`));diagnostics.getRange(`B6:B${5+checks.length}`).format.numberFormat="0.0000000000";diagnostics.getRange(`C6:C${5+checks.length}`).format.fill=paleGreen;
diagnostics.getRange("E5:H5").values=[["复现信息","数值","说明",""]];header(diagnostics.getRange("E5:H5"));diagnostics.getRange("E6:G12").values=[
  ["模拟次数",config.simulation.draws,"100,000轮"],["随机种子",config.simulation.master_seed,"固定"],["主重叠情景",config.primary_overlap_scenario,"证据校准"],["D残余κ",config.primary_diagnostic_residual_log_hr_fraction,"主值0.5"],["旧版文件","未覆盖","独立目录"],["脚本","joint_effect_monte_carlo_evidence_calibrated.py","可复现"],["工作簿","证据校准版","结果快照"],
];body(diagnostics.getRange("E6:G12"));diagnostics.getRange("F6:G12").format.wrapText=true;diagnostics.freezePanes.freezeRows(5);for(const [c,w] of Object.entries({A:32,B:28,C:13,D:4,E:22,F:38,G:28,H:10}))diagnostics.getRange(`${c}1:${c}25`).format.columnWidth=w;

wb.recalculate();
const summaryInspect=await wb.inspect({kind:"table",sheetId:"综合主结果",range:"A1:L20",include:"values,formulas",tableMaxRows:24,tableMaxCols:14});
const formulaErrors=await wb.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",options:{useRegex:true,maxResults:300},summary:"final formula error scan"});
await fs.mkdir(previewDir,{recursive:true});
for(const [sheetName,range] of [["综合主结果","A1:L20"],["重叠约束",`A1:N${12+overlapRows.length}`],["敏感性",`A1:L${5+sens.length}`],["条件概率证据",`A1:R${5+conditionalRows.length}`],["D残余证据",`A1:F${5+residualRows.length}`],["运行诊断","A1:H20"]]){
  const img=await wb.render({sheetName,range,scale:1.1,format:"png"});await fs.writeFile(path.join(previewDir,`${sheetName}.png`),new Uint8Array(await img.arrayBuffer()));
}
const exported=await SpreadsheetFile.exportXlsx(wb);await exported.save(outputPath);
const bytes=await fs.readFile(outputPath);const sha256=createHash("sha256").update(bytes).digest("hex");
const saved=await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
const savedSheets=await saved.inspect({kind:"sheet",include:"id,name",maxChars:5000});
const savedSummary=await saved.inspect({kind:"table",sheetId:"综合主结果",range:"A5:L13",include:"values,formulas",tableMaxRows:15,tableMaxCols:14});
const savedOverlap=await saved.inspect({kind:"table",sheetId:"重叠约束",range:"A5:H9",include:"values,formulas",tableMaxRows:10,tableMaxCols:10});
const savedConditionalEvidence=await saved.inspect({kind:"table",sheetId:"条件概率证据",range:`A5:R${5+conditionalRows.length}`,include:"values,formulas",tableMaxRows:15,tableMaxCols:20});
const savedResidualEvidence=await saved.inspect({kind:"table",sheetId:"D残余证据",range:`A5:F${5+residualRows.length}`,include:"values,formulas",tableMaxRows:10,tableMaxCols:8});
const savedErrors=await saved.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",options:{useRegex:true,maxResults:300},summary:"saved workbook formula error scan"});
const manifestPath=path.join(inputDir,"run_manifest.json");const manifest=JSON.parse(await fs.readFile(manifestPath,"utf8"));manifest.outputs_sha256=manifest.outputs_sha256??{};manifest.outputs_sha256["build_evidence_calibrated_workbook.mjs"]=createHash("sha256").update(await fs.readFile(path.join(inputDir,"build_evidence_calibrated_workbook.mjs"))).digest("hex");manifest.final_workbook={file:path.basename(outputPath),bytes:bytes.byteLength,sha256,sheets:9};await fs.writeFile(manifestPath,JSON.stringify(manifest,null,2),"utf8");
await fs.writeFile(path.join(previewDir,"verification.json"),JSON.stringify({summary:summaryInspect.ndjson,formulaErrors:formulaErrors.ndjson,savedSheets:savedSheets.ndjson,savedSummary:savedSummary.ndjson,savedOverlap:savedOverlap.ndjson,savedConditionalEvidence:savedConditionalEvidence.ndjson,savedResidualEvidence:savedResidualEvidence.ndjson,savedErrors:savedErrors.ndjson,outputPath,sha256},null,2));
console.log(JSON.stringify({outputPath,sheets:9,sha256,formulaErrors:formulaErrors.ndjson,savedErrors:savedErrors.ndjson},null,2));
