/* 公開前検証用。架空企業のみ。実在企業の数値は検証した一次資料に基づき追加してください。 */
window.MCL_COMPANIES = [
 {id:'demo-a',name:'【架空】サンプル現職メーカー',aliases:['サンプル現職'],demo:true,sector:'産業機械',period:'架空の2025年度',scope:'連結（給与のみ単体の想定）',sourceLabel:'架空データ：実在の決算資料ではありません',sourceUrl:'',revenue:1000,operatingProfit:80,revenuePrev:950,operatingCashFlow:90,equityRatio:48,averageSalary:680,salaryScope:'架空の単体平均',employees:4500},
 {id:'demo-b',name:'【架空】サンプル検討先メーカー',aliases:['サンプル検討先'],demo:true,sector:'電子機器',period:'架空の2025年度',scope:'連結（給与のみ単体の想定）',sourceLabel:'架空データ：実在の決算資料ではありません',sourceUrl:'',revenue:1200,operatingProfit:216,revenuePrev:1050,operatingCashFlow:130,equityRatio:62,averageSalary:820,salaryScope:'架空の単体平均',employees:5200}
];
/* 単位：売上高・営業利益・営業CF＝億円、平均年間給与＝万円、自己資本比率＝%。
   実在企業は一次資料と数値を照合し、出典URL、決算期、連結/単体の範囲を必ず記載。
   出典が未検証の値や、比較不能な指標は null にしてください。 */
