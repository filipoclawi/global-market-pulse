const assert=require('node:assert/strict');const M=require('../assets/market.js');
const sample=[{id:'a',name:'A',points:[['2024-01-02',100],['2024-01-03',110],['2025-01-02',121]]},{id:'b',name:'B',points:[['2024-01-02',200],['2025-01-02',180]]}];
assert.deepEqual(M.findBasePoint(sample[0].points,'2024-01-02'),['2024-01-02',100]);
assert.equal(M.findBasePoint(sample[0].points,'2023-01-01'),null);
assert.ok(Math.abs(M.changePct(100,121)-21)<1e-10);
const stats=M.aggregateChanges(sample,'2024-01-02');assert.equal(stats.coverage,2);assert.equal(stats.advancing,1);assert.ok(Math.abs(stats.mean-5.5)<1e-10);assert.ok(Math.abs(stats.median-5.5)<1e-10);assert.equal(stats.leader.name,'A');
const sameDay=M.aggregateChanges(sample,'2025-01-02');assert.equal(sameDay.coverage,2);assert.equal(sameDay.mean,0);
assert.equal(M.rangeStart('YTD','2026-07-18'),'2026-01-01');assert.equal(M.oneYearAgo('2026-07-18'),'2025-07-18');
const rebased=M.rebase([['a',4],['b',6]]);assert.deepEqual(rebased,[['a',100],['b',150]]);
const history=M.aggregateHistory([...sample,{id:'c',name:'C',points:[['2024-01-02',300],['2025-01-02',300]]}],'2024-01-02',100);assert.ok(history.length>=2);assert.equal(history[0][1],100);
const entrants=[
 {points:[['2024-01-01',100],['2024-01-02',101],['2024-01-03',102],['2024-01-04',103]]},
 {points:[['2024-01-01',200],['2024-01-02',202],['2024-01-03',204],['2024-01-04',206]]},
 {points:[['2024-01-01',300],['2024-01-02',303],['2024-01-03',306],['2024-01-04',309]]},
 {points:[['2024-01-03',1000],['2024-01-04',1010]]}
];
const entrantHistory=M.aggregateHistory(entrants,'2024-01-01',100);const entry=entrantHistory.findIndex(p=>p[0]==='2024-01-03');assert.ok(entry>0);assert.ok(Math.abs(M.changePct(entrantHistory[entry-1][1],entrantHistory[entry][1]))<2);
console.log('market math tests passed');
