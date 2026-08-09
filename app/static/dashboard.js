const $=id=>document.getElementById(id);
const numberFormat=new Intl.NumberFormat('zh-CN');

function formatDateInput(date){
  const year=date.getFullYear();
  const month=String(date.getMonth()+1).padStart(2,'0');
  const day=String(date.getDate()).padStart(2,'0');
  return `${year}-${month}-${day}`;
}

function setDateRange(days){
  if(days==='all'){
    $('dateFrom').value='';
    $('dateTo').value='';
  }else{
    const end=new Date();
    const start=new Date();
    start.setDate(end.getDate()-Number(days)+1);
    $('dateFrom').value=formatDateInput(start);
    $('dateTo').value=formatDateInput(end);
  }
  document.querySelectorAll('.quick-button').forEach(button=>button.classList.toggle('active',button.dataset.days===String(days)));
}

function queryParams(){
  const params=new URLSearchParams();
  if($('dateFrom').value)params.set('date_from',new Date(`${$('dateFrom').value}T00:00:00`).toISOString());
  if($('dateTo').value)params.set('date_to',new Date(`${$('dateTo').value}T23:59:59.999`).toISOString());
  return params;
}

function formatNumber(value){
  return numberFormat.format(Number(value)||0);
}

function formatDuration(milliseconds){
  const value=Number(milliseconds)||0;
  if(value<1000)return `${numberFormat.format(value)} ms`;
  const seconds=value/1000;
  if(seconds<60)return `${seconds.toFixed(seconds<10?1:0)} 秒`;
  const minutes=seconds/60;
  if(minutes<60)return `${minutes.toFixed(minutes<10?1:0)} 分钟`;
  const hours=minutes/60;
  return `${hours.toFixed(hours<10?1:0)} 小时`;
}

function formatPercent(ratio){
  const percent=(Number(ratio)||0)*100;
  return `${percent.toFixed(percent>0&&percent<1?1:percent%1?1:0)}%`;
}

function renderMetrics(data){
  $('taskNum').textContent=formatNumber(data.task_num);
  $('projectNum').textContent=formatNumber(data.project_num);
  $('issueNum').textContent=formatNumber(data.issue_num);
  $('redIssueRatio').textContent=formatPercent(data.red_issue_ratio);
  $('redIssueCount').textContent=`红色问题 ${formatNumber(data.red_issue_num)} 个`;

  const reviewRatio=data.file_num?data.reviewed_file_num/data.file_num:0;
  const reviewPercent=Math.max(0,Math.min(100,reviewRatio*100));
  $('reviewProgress').textContent=formatPercent(reviewRatio);
  $('reviewedFilesText').textContent=`已审 ${formatNumber(data.reviewed_file_num)} / 总文件 ${formatNumber(data.file_num)}`;
  $('fileNum').textContent=formatNumber(data.file_num);
  $('reviewedFileNum').textContent=formatNumber(data.reviewed_file_num);
  $('reviewProgressBar').style.width=`${reviewPercent}%`;
  $('reviewProgressBar').parentElement.setAttribute('aria-valuenow',String(Math.round(reviewPercent)));

  const redPercent=Math.max(0,Math.min(100,(Number(data.red_issue_ratio)||0)*100));
  $('redRatioRing').style.setProperty('--ratio',String(redPercent));
  $('ringRatio').textContent=formatPercent(data.red_issue_ratio);
  $('compositionIssueNum').textContent=formatNumber(data.issue_num);
  $('compositionRedNum').textContent=formatNumber(data.red_issue_num);
  $('otherIssueNum').textContent=formatNumber(Math.max(0,data.issue_num-data.red_issue_num));

  $('totalTokens').textContent=formatNumber(data.llm_total_tokens);
  $('promptTokens').textContent=formatNumber(data.llm_prompt_tokens);
  $('completionTokens').textContent=formatNumber(data.llm_completion_tokens);
  $('llmElapsed').textContent=formatDuration(data.llm_elapsed_ms);
  $('toolCallNum').textContent=formatNumber(data.tool_call_num);
  $('modelRoundNum').textContent=formatNumber(data.model_round_num);
  $('taskTrendTotal').textContent=`共 ${formatNumber(data.task_num)}`;
  $('issueTrendTotal').textContent=`共 ${formatNumber(data.issue_num)}`;
}

function chartPath(points,x,y){
  return points.map((point,index)=>`${index?'L':'M'} ${x(index).toFixed(2)} ${y(point).toFixed(2)}`).join(' ');
}

function renderChart(containerId,points,valueKey,color,fillId){
  const container=$(containerId);
  if(!points.length){
    container.innerHTML='<div class="chart-empty">当前统计范围内没有趋势数据</div>';
    return;
  }
  const width=720;
  const height=270;
  const margin={top:18,right:18,bottom:38,left:48};
  const plotWidth=width-margin.left-margin.right;
  const plotHeight=height-margin.top-margin.bottom;
  const values=points.map(point=>Math.max(0,Number(point[valueKey])||0));
  const maxValue=Math.max(1,...values);
  const x=index=>margin.left+(points.length===1?plotWidth/2:index*plotWidth/(points.length-1));
  const y=value=>margin.top+plotHeight-(value/maxValue)*plotHeight;
  const path=chartPath(values,x,y);
  const area=`${path} L ${x(values.length-1).toFixed(2)} ${(margin.top+plotHeight).toFixed(2)} L ${x(0).toFixed(2)} ${(margin.top+plotHeight).toFixed(2)} Z`;
  const gridLines=Array.from({length:5},(_,index)=>{
    const ratio=index/4;
    const lineY=margin.top+plotHeight*ratio;
    const label=Math.round(maxValue*(1-ratio));
    return `<line class="chart-grid-line" x1="${margin.left}" y1="${lineY}" x2="${width-margin.right}" y2="${lineY}"></line><text class="chart-axis-label" x="${margin.left-9}" y="${lineY+4}" text-anchor="end">${label}</text>`;
  }).join('');
  const labelIndexes=new Set(Array.from({length:Math.min(6,points.length)},(_,index)=>Math.round(index*(points.length-1)/Math.max(1,Math.min(6,points.length)-1))));
  const xLabels=points.map((point,index)=>labelIndexes.has(index)?`<text class="chart-axis-label" x="${x(index)}" y="${height-12}" text-anchor="middle">${point.date.slice(5)}</text>`:'').join('');
  const circles=points.map((point,index)=>`<circle class="chart-point" cx="${x(index)}" cy="${y(values[index])}" r="4" fill="${color}"><title>${point.date}：${formatNumber(values[index])}</title></circle>`).join('');
  container.innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${container.getAttribute('aria-label')}"><defs><linearGradient id="${fillId}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${color}" stop-opacity=".20"></stop><stop offset="100%" stop-color="${color}" stop-opacity=".015"></stop></linearGradient></defs>${gridLines}<path d="${area}" fill="url(#${fillId})"></path><path class="chart-line" d="${path}" stroke="${color}"></path>${circles}${xLabels}</svg>`;
}

function updateRangeDescription(){
  const from=$('dateFrom').value;
  const to=$('dateTo').value;
  if(from&&to)$('rangeDescription').textContent=`统计 ${from} 至 ${to} 创建的任务`;
  else if(from)$('rangeDescription').textContent=`统计 ${from} 之后创建的任务`;
  else if(to)$('rangeDescription').textContent=`统计 ${to} 之前创建的任务`;
  else $('rangeDescription').textContent='统计全部历史任务';
}

async function loadDashboard(){
  const from=$('dateFrom').value;
  const to=$('dateTo').value;
  if(from&&to&&from>to){
    $('statusMessage').textContent='开始日期不能晚于结束日期';
    $('statusMessage').classList.add('error');
    return;
  }
  $('queryButton').disabled=true;
  $('queryButton').textContent='正在统计...';
  $('statusMessage').textContent='正在汇总任务、文件与模型调用数据...';
  $('statusMessage').classList.remove('error');
  try{
    const response=await fetch(`/api/admin/dashboard?${queryParams()}`);
    if(!response.ok){
      let message='看板数据加载失败';
      try{message=(await response.json()).detail||message}catch{}
      throw new Error(message);
    }
    const data=await response.json();
    renderMetrics(data);
    renderChart('taskChart',data.daily_trends,'task_num','#087f5b','taskArea');
    renderChart('issueChart',data.daily_trends,'issue_num','#c92a2a','issueArea');
    updateRangeDescription();
    $('lastUpdated').textContent=`更新于 ${new Date().toLocaleString('zh-CN',{hour12:false})}`;
    $('statusMessage').textContent=`已汇总 ${formatNumber(data.task_num)} 个任务、${formatNumber(data.file_num)} 个文件`;
  }catch(error){
    $('statusMessage').textContent=error.message;
    $('statusMessage').classList.add('error');
  }finally{
    $('queryButton').disabled=false;
    $('queryButton').textContent='更新看板';
  }
}

$('filterForm').addEventListener('submit',event=>{
  event.preventDefault();
  document.querySelectorAll('.quick-button').forEach(button=>button.classList.remove('active'));
  loadDashboard();
});
document.querySelectorAll('.quick-button').forEach(button=>button.addEventListener('click',()=>{
  setDateRange(button.dataset.days);
  loadDashboard();
}));

setDateRange(30);
loadDashboard();
