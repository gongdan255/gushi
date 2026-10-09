'use strict';
async function loadInsights(){
  try{
    const d=await api('/api/insights');
    chart('#season-chart',{grid:{left:55,right:22,top:30,bottom:35},tooltip:{trigger:'axis',axisPointer:{type:'shadow'},formatter:p=>`${p[0].name} · ${p[0].value.toLocaleString()} 篇`},xAxis:{type:'category',data:d.seasons.map(x=>x.name),axisTick:{show:false},axisLine:{lineStyle:{color:'#c3cbb9'}},axisLabel:{fontSize:16,color:'#344c41'}},yAxis:{type:'value',minInterval:1,axisLabel:{fontSize:10},splitLine:{lineStyle:{color:'#e9ecdf',type:'dashed'}}},series:[{type:'bar',barMaxWidth:40,label:{show:true,position:'top',color:'#657867',formatter:p=>p.value.toLocaleString()},data:d.seasons.map((x,i)=>({value:x.value,itemStyle:{color:['#8da477','#d0b573','#b87855','#7797a1'][i],borderRadius:[3,3,0,0]}}))}]},p=>explore({kind:'诗词曲',body:p.name}));
    const max=Math.max(1,...d.links.map(x=>x.value)),nodeMax=Math.max(1,...d.nodes.map(x=>x.value));
    chart('#cooccurrence-chart',{tooltip:{formatter:p=>p.dataType==='edge'?`${p.data.source} — ${p.data.target}<br>同篇共现 ${p.data.value.toLocaleString()} 篇`:`${p.name}<br>正文含字 ${p.value.toLocaleString()} 篇`},series:[{type:'graph',layout:'circular',circular:{rotateLabel:false},left:35,right:35,top:30,bottom:35,roam:false,label:{show:true,fontSize:16,color:'#fffefa'},emphasis:{focus:'adjacency',lineStyle:{opacity:1}},data:d.nodes.map(n=>({...n,symbolSize:28+18*n.value/nodeMax,itemStyle:{color:'#526f59'}})),links:d.links.map(l=>({...l,lineStyle:{width:1+5*l.value/max,color:'#9aac8d',opacity:.55,curveness:.12}}))}]},p=>explore({kind:'诗词曲',body:p.dataType==='edge'?[p.data.source,p.data.target].join(','):p.name}));
  }catch(e){for(const id of ['season-chart','cooccurrence-chart'])$('#'+id).textContent='统计暂未加载，请刷新重试。';}
}
