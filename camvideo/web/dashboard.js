/* Calendar periods use the PC's local day from the backend, never UTC. */
const Dashboard = (() => {
  function date(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) throw Error('Informe as duas datas.');
    const d = new Date(value + 'T12:00:00');
    if (!Number.isFinite(+d) || iso(d) !== value) throw Error('Data inválida.');
    return d;
  }
  function iso(d) {
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  }
  function shift(value, days) { const d = date(value); d.setDate(d.getDate()+days); return iso(d); }
  function range(preset, today, start, end) {
    date(today);
    if (preset === 'custom') {
      date(start); date(end);
      if (start > end) throw Error('A data inicial deve ser anterior ou igual à final.');
      if (end > today) throw Error('Escolha datas até hoje.');
      return {start, end};
    }
    if (preset === 'yesterday') return {start:shift(today,-1),end:shift(today,-1)};
    const days = {'today':1,'7':7,'15':15,'30':30}[preset] || 1;
    return {start:shift(today,1-days),end:today};
  }
  function aggregate(analytics, period) {
    const tasks = new Map(), phones = new Map();
    for (const p of analytics.byPhone || []) phones.set(p.name, 0);
    for (const t of analytics.byTask || []) tasks.set(t.name, {name:t.name,seconds:0,phones:new Map()});
    const chart = new Map();
    for (let day=period.start; day<=period.end; day=shift(day,1)) chart.set(day,0);
    let seconds = 0;
    for (const row of analytics.historyRows || []) {
      if (row.day < period.start || row.day > period.end) continue;
      const value = Math.max(0,Number(row.seconds)||0);
      if (!Number.isFinite(value)) continue;
      seconds += value;
      chart.set(row.day,(chart.get(row.day)||0)+value);
      phones.set(row.phone,(phones.get(row.phone)||0)+value);
      if (!tasks.has(row.task)) tasks.set(row.task,{name:row.task,seconds:0,phones:new Map()});
      const task = tasks.get(row.task); task.seconds += value;
      task.phones.set(row.phone,(task.phones.get(row.phone)||0)+value);
    }
    return {seconds, activeTasks:[...tasks.values()].filter(t=>t.seconds>0).length,
      chart:[...chart].map(([date,seconds])=>({date,seconds})),
      byPhone:[...phones].map(([name,seconds])=>({name,seconds})).sort((a,b)=>b.seconds-a.seconds),
      byTask:[...tasks.values()].map(t=>({...t,phones:[...phones.keys()].map(name=>({name,seconds:t.phones.get(name)||0}))})).sort((a,b)=>b.seconds-a.seconds)};
  }
  function reais(seconds, rate) { return Math.max(0,seconds)/3600*4*rate; }
  return {range, aggregate, reais};
})();
if (typeof module !== 'undefined') module.exports = Dashboard;
