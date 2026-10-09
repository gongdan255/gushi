'use strict';
function renderPuzzleIntro(){
  $$('[data-game]').forEach(b=>b.setAttribute('aria-selected',b.dataset.game==='puzzle'));
  $('#game-rules').textContent='每轮五首四句短诗，每题 20 分。点击诗句依次排列，点击已排诗句可移回。提交后查看原文；错题可单独重练，重练不计入最高分。顺序以本库选本为准。';
  $('#game-area').innerHTML='<div class="game-intro"><div class="game-icon">序</div><h2>拾起散句，拼回一首诗。</h2><p>让打乱的四句诗，重新归位。<br>从起句到收笔，读懂一首诗的次序。</p><div class="badge">每轮 5 题 · 点击排序 · 不限时</div><br><button class="primary-button" id="start-puzzle">开始拼图 →</button></div>';
}
async function startPuzzle(){
  const pending={loading:true};state.puzzle=pending;
  $('#start-puzzle').disabled=true;$('#start-puzzle').textContent='正在准备诗句…';
  try{const d=await api('/api/puzzle');if(state.game!=='puzzle'||state.puzzle!==pending)return;
    if(!d.questions.length)throw Error('暂时没有合适的拼图题目。');
    beginPuzzle(d.questions);
  }catch(e){if(state.game==='puzzle'&&state.puzzle===pending){state.puzzle=null;renderPuzzleIntro();errorToast(e);}}
}
function beginPuzzle(questions,practice=false){state.puzzle={questions,practice,index:0,picked:[],answers:[],submitted:false};renderPuzzle();}
function renderPuzzle(){
  const s=state.puzzle,q=s.questions[s.index];
  $('#game-area').innerHTML=`<div class="game-info"><span>${s.practice?'错题重练':'诗句拼图'} / 第 ${s.index+1} / ${s.questions.length} 题</span><span>已答对 ${s.answers.filter(a=>a.correct).length} 题</span></div><div class="progress"><span style="width:${s.index/s.questions.length*100}%"></span></div><div class="puzzle-heading"><small>${esc(q.author)}</small><h2>《${esc(q.title)}》</h2><p>按原诗顺序点击下方诗句，填入四个位置。</p></div><ol class="puzzle-slots" aria-label="已排列诗句">${Array.from({length:4},(_,i)=>`<li><span class="slot-number">${i+1}</span>${s.picked[i]!==undefined?`<button data-puzzle-remove="${i}" ${s.submitted?'disabled':''} aria-label="移回第${i+1}句：${esc(q.pieces[s.picked[i]])}">${esc(q.pieces[s.picked[i]])}</button>`:'<span class="slot-empty">等待诗句归位</span>'}</li>`).join('')}</ol><div class="puzzle-pieces" aria-label="待排列诗句">${q.pieces.map((line,i)=>`<button class="puzzle-piece" data-puzzle-pick="${i}" ${s.submitted||s.picked.includes(i)?'disabled':''}>${esc(line)}</button>`).join('')}</div><div class="puzzle-controls"><button class="text-button" id="puzzle-undo" ${s.submitted||!s.picked.length?'disabled':''}>撤回一句</button><button class="text-button" id="puzzle-reset" ${s.submitted||!s.picked.length?'disabled':''}>重新排列</button><button class="primary-button" id="puzzle-submit" ${s.submitted||s.picked.length!==4?'disabled':''}>提交答案</button></div><div id="puzzle-feedback" class="feedback" role="status">${s.submitted?(s.answers.at(-1).correct?'✓ 次序正确，整首诗已归位。':'○ 再读一遍，记住诗句间的衔接。'):s.picked.length===4?'四句已齐，可以提交答案。':'点击已排列的诗句，可以将它移回。'}</div>${s.submitted?`<div class="puzzle-solution"><small>原诗顺序</small><p>${q.answer.map(esc).join('<br>')}</p><button class="text-button" data-open="${q.poemId}">阅读原文与出处 ↗</button></div><div class="game-bottom"><button class="primary-button" id="puzzle-next">${s.index+1===s.questions.length?'查看成绩':'下一题 →'}</button></div>`:''}`;
}
function finishPuzzle(){
  const s=state.puzzle,correct=s.answers.filter(a=>a.correct).length,wrong=s.answers.filter(a=>!a.correct).map(a=>a.question),score=correct*20;
  s.finished=true;s.wrong=wrong;
  if(!s.practice){state.records.puzzleBest=Math.max(state.records.puzzleBest||0,score);save();records();}
  $('#game-area').innerHTML=`<div class="game-intro"><span class="eyebrow">${s.practice?'错题重练完成':'拼图完成'}</span><div class="score-big">${s.practice?correct:score}<small style="font-size:18px"> ${s.practice?'题正确':'分'}</small></div><h2>${wrong.length?'再读一次，让诗句留在心里。':'句句归位，一首一重逢。'}</h2><p>答对 ${correct} / ${s.questions.length} 题${s.practice?' · 不计入最高分':''}</p><button class="primary-button" id="puzzle-again">再来一轮</button> ${wrong.length?'<button class="outline-button" id="puzzle-retry">重练错题</button>':''}</div>${s.answers.map(a=>`<div class="review-item"><small>${a.correct?'✓ 次序正确':'○ 待温习'}</small><br>《${esc(a.question.title)}》 · ${esc(a.question.author)}<br>${a.question.answer.map(esc).join('，')}。<br><button class="text-button" data-open="${a.question.poemId}">查看原文 ↗</button></div>`).join('')}`;
}
document.addEventListener('click',e=>{
  const b=e.target.closest('button');if(!b)return;
  if(b.id==='start-puzzle'){startPuzzle();return;}
  if(b.id==='puzzle-again'){setGame('puzzle');return;}
  const s=state.puzzle;if(state.game!=='puzzle'||!s||s.loading)return;
  if(b.id==='puzzle-retry'&&s.finished){beginPuzzle(s.wrong,true);return;}
  if(s.finished)return;
  if(b.id==='puzzle-next'&&s.submitted){if(++s.index===s.questions.length)finishPuzzle();else{s.picked=[];s.submitted=false;renderPuzzle();}return;}
  if(s.submitted)return;
  if(b.dataset.puzzlePick!==undefined){const i=+b.dataset.puzzlePick;if(!s.picked.includes(i)&&s.picked.length<4)s.picked.push(i);else return;}
  else if(b.dataset.puzzleRemove!==undefined)s.picked.splice(+b.dataset.puzzleRemove,1);
  else if(b.id==='puzzle-undo')s.picked.pop();
  else if(b.id==='puzzle-reset')s.picked=[];
  else if(b.id==='puzzle-submit'&&s.picked.length===4){const q=s.questions[s.index];s.submitted=true;s.answers.push({question:q,correct:s.picked.every((i,n)=>q.pieces[i]===q.answer[n])});}
  else return;
  renderPuzzle();
});
