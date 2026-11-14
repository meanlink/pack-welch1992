import {datasets,jobs} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {table} from '../components/common/table.js';
import {esc,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
function pairedParam(meta){return meta.parameters.find(p=>p.key==='analysis');}
function shiftParam(meta){return meta.parameters.find(p=>p.key==='shift');}
export async function workbench(){
 workspace.datasets=await datasets.list();const m=workspace.meta;
 return heading('03 / ANALYSIS LAB',m.workbench_title,'选择业务批次和分析口径。参数、输入指纹与计算结论随任务保存，便于复核和复现。')+'<div class="workbench-grid"><section class="panel"><form id="job-form"><label>分析任务名称<input name="name" required minlength="2" value="'+esc(m.name)+' · 复核试算"></label><label>数据批次<select name="dataset_id" required>'+workspace.datasets.map(d=>'<option value="'+d.id+'" data-station="'+(d.station_field?'1':'0')+'">'+esc(d.name)+' · '+d.rows+' 条'+(d.station_field?'':' · 旧批次无工位字段')+'</option>').join('')+'</select></label><div class="parameter-grid">'+m.parameters.map(p=>'<label>'+esc(p.label)+(p.type==='select'?'<select name="param-'+esc(p.key)+'"'+(p.key==='analysis'?' id="param-analysis"':'')+'>'+p.options.map(o=>'<option value="'+esc(o.value)+'" '+(o.value==p.default?'selected':'')+'>'+esc(o.label)+'</option>').join('')+'</select>':'<input type="number" step="any" name="param-'+esc(p.key)+'" value="'+esc(p.default)+'" min="'+esc(p.min??'')+'" max="'+esc(p.max??'')+'" required>')+'</label>').join('')+'</div><p class="warning" id="pair-guard" hidden></p><p class="hint" id="pair-hint"></p><button type="submit" class="primary" '+(session.user.role==='viewer'||!workspace.datasets.length?'disabled':'')+'>'+esc(m.action_label||'执行分析')+' ↗</button><p class="hint">提交后由后台任务计算。观察员可查看参数和结果，无法提交。</p></form></section><section class="method-sheet"><p class="eyebrow">METHOD / BUSINESS RULE</p><h2>'+esc(m.method)+'</h2><p>'+esc(m.tagline)+'</p><h3>业务判读边界</h3><ul>'+m.limitations.map(v=>'<li>'+esc(v)+'</li>').join('')+'</ul><div class="method-trace"><span>输入</span><strong>'+esc(m.dataset_name)+'</strong><span>输出</span><strong>可复核结果 / 参数版本 / 分发归档</strong></div></section></div>';
}
export function bindWorkbench(){
 const form=document.querySelector('#job-form');
 if(!form)return;
 const datasetSelect=form.querySelector('[name=dataset_id]');
 const analysisSelect=form.querySelector('#param-analysis');
 const guard=form.querySelector('#pair-guard');
 const hint=form.querySelector('#pair-hint');
 const meta=workspace.meta;
 function currentDataset(){return workspace.datasets.find(d=>d.id===Number(datasetSelect.value));}
 function refreshPairGuard(){
   if(!pairedParam(meta))return;
   const d=currentDataset();
   const paired=analysisSelect&&analysisSelect.value==='paired';
   const shift=shiftParam(meta)?form.querySelector('[name=param-shift]')?.value:null;
   if(paired&&d&&!d.station_field){
     guard.hidden=false;guard.textContent='该批次为缺少工位字段的旧批次，无法按工位配对，后端将整次拒绝；请改用独立样本 Welch 比较。';
     hint.textContent='';
   }else{
     guard.hidden=true;guard.textContent='';
     hint.textContent=paired?('按工位配对：同工位同班次两动作各一段才计入；缺对、同组重复或跨班配对将整次拒绝并列出问题工位。'+(shift&&shift!=='全部'?'当前限定「'+shift+'」，同样核对该班次内的配对完整性。':'选择具体班次时也会核对该班次的配对完整性。')):'独立样本 Welch 比较不要求工位字段，旧批次照常可用。';
   }
 }
 datasetSelect?.addEventListener('change',refreshPairGuard);
 analysisSelect?.addEventListener('change',refreshPairGuard);
 form.querySelector('[name=param-shift]')?.addEventListener('change',refreshPairGuard);
 refreshPairGuard();
 submit(form,async f=>{const params={};for(const p of workspace.meta.parameters){const value=f.get('param-'+p.key);params[p.key]=p.type==='number'?Number(value):value;}
   const chosen=workspace.datasets.find(d=>d.id===Number(f.get('dataset_id')));
   if(params.analysis==='paired'&&chosen&&!chosen.station_field){notify('该批次缺少工位字段，不能做配对分析，请改用独立样本 Welch 比较',true);return;}
   const j=await jobs.create({name:f.get('name'),dataset_id:Number(f.get('dataset_id')),params});workspace.selectedJob=j.id;notify('分析任务已提交');location.hash='#/results/'+j.id;});
}
