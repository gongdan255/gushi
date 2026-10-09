'use strict';
function setupCustomFeihua(){
  $('.keyword-options').closest('.game-intro').classList.add('feihua-intro');
  $('.keyword-options').setAttribute('aria-label','可选令字，共两行，可左右滚动');
  const host=document.createElement('div');host.className='custom-feihua';
  host.innerHTML='<label for="custom-keyword">自由选字</label><input id="custom-keyword" placeholder="如：愁" autocomplete="off" aria-describedby="keyword-hint" maxlength="8"><div id="keyword-hint" role="status">输入一个汉字，看看诗词中有哪些相关词语。</div><div id="keyword-words" class="keyword-words"></div>';
  $('.keyword-options').after(host);
  const help=document.createElement('div');help.className='keyword-scroll-hint';help.textContent='36 个令字 · 两行排列，左右滑动查看更多';
  $('.keyword-options').after(help);
  const examples=document.createElement('div');examples.className='keyword-examples';examples.hidden=true;examples.setAttribute('aria-live','polite');host.append(examples);
  const input=$('#custom-keyword'),hint=$('#keyword-hint'),words=$('#keyword-words'),start=$('#start-fly');
  let ticket=0,timer,exampleTicket=0;
  function change(){
    clearTimeout(timer);const request=++ticket;delete input.dataset.chosen;words.replaceChildren();
    exampleTicket++;examples.hidden=true;examples.replaceChildren();
    const value=input.value.trim();
    if(!value){if(!$('.keyword-options .selected')){const first=$('[data-keyword]');first.classList.add('selected');first.setAttribute('aria-pressed','true');}start.disabled=false;hint.textContent='输入一个汉字，看看诗词中有哪些相关词语。';return;}
    start.disabled=true;
    if(!/^[\u4e00-\u9fff]$/.test(value)){hint.textContent='请输入一个汉字，不要输入词组、数字或标点。';return;}
    hint.textContent='正在寻找相关词语…';
    timer=setTimeout(async()=>{
      try{const d=await api('/api/feihua/suggestions?'+new URLSearchParams({keyword:value}));
        if(!input.isConnected||request!==ticket)return;
        if(!d.available){hint.textContent='诗词库中暂未找到这个字，请换一个字。';return;}
        input.dataset.chosen=d.keyword;start.disabled=false;
        $$('[data-keyword]').forEach(b=>{b.classList.remove('selected');b.setAttribute('aria-pressed','false');});
        hint.textContent=`已选令字“${d.keyword}” · ${d.words.length?'相关词语来自库内部分诗词，供联想参考':'暂未提取到相关词语，仍可开令'}`;
        words.innerHTML=d.words.map(w=>`<button type="button" data-related-word="${esc(w)}" aria-pressed="false">${esc(w)}</button>`).join('');
        if(d.words.length)hint.textContent+=' · 点击词语查看诗句';
      }catch(e){if(input.isConnected&&request===ticket)hint.textContent=e.message;}
    },300);
  }
  input.addEventListener('input',e=>{if(!e.isComposing)change();});
  input.addEventListener('compositionend',change);
  words.addEventListener('click',async e=>{
    const button=e.target.closest('[data-related-word]');if(!button)return;
    const word=button.dataset.relatedWord,request=++exampleTicket;
    $$('[data-related-word]',words).forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
    examples.hidden=false;examples.textContent='正在查找相关诗句…';
    try{const d=await api('/api/poems?'+new URLSearchParams({q:word,kind:'诗词曲'}));
      if(!host.isConnected||request!==exampleTicket)return;
      examples.innerHTML=`<div class="example-heading">含“${esc(word)}”的作品 <button type="button" class="text-button" data-hide-examples>收起 ↑</button></div>`+(d.items.length?d.items.slice(0,3).map(p=>{const paragraph=p.paragraphs.find(line=>line.includes(word));return `<div class="keyword-example"><p>${esc(paragraph||p.paragraphs[0])}</p><button type="button" class="text-button" data-open="${p.id}">《${esc(p.title)}》 · ${esc(p.author)} ↗</button></div>`;}).join(''):'<p>暂未找到相关作品。</p>');
    }catch(e){if(host.isConnected&&request===exampleTicket)examples.textContent=e.message;}
  });
  examples.addEventListener('click',e=>{if(e.target.closest('[data-hide-examples]')){exampleTicket++;examples.hidden=true;$$('[data-related-word]',words).forEach(b=>b.setAttribute('aria-pressed','false'));}});
  $('.keyword-options').addEventListener('click',e=>{if(!e.target.closest('[data-keyword]'))return;input.value='';change();});
}
