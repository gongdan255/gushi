'use strict';
// Retain the native selects as the source of values for existing search filters.
const filterDropdowns=[];
for(const id of ['collection-filter','author-filter']){
  const select=document.getElementById(id),oldLabel=select.parentElement;
  const title=oldLabel.firstChild.textContent.trim();
  const field=document.createElement('div');field.className='dropdown-field';
  const label=document.createElement('span');label.textContent=title;label.id=id+'-label';
  const box=document.createElement('div');box.className='filter-dropdown';
  const trigger=document.createElement('button');trigger.type='button';trigger.className='dropdown-trigger';
  trigger.setAttribute('aria-haspopup','dialog');trigger.setAttribute('aria-expanded','false');trigger.setAttribute('aria-labelledby',label.id+' '+id+'-value');
  const value=document.createElement('span');value.id=id+'-value';trigger.append(value);
  const menu=document.createElement('div');menu.className='dropdown-menu';menu.id=id+'-menu';menu.hidden=true;menu.setAttribute('role','dialog');menu.setAttribute('aria-label',title+'选择');trigger.setAttribute('aria-controls',menu.id);
  const input=document.createElement('input');input.type='search';input.placeholder='搜索'+title+'…';input.setAttribute('aria-label','搜索'+title);input.autocomplete='off';
  const list=document.createElement('div');list.className='dropdown-options';
  const hint=document.createElement('div');hint.className='dropdown-hint';hint.textContent=id==='author-filter'?'常见作者列表；其他作者可在上方搜索':'选择选集查看收录作品';
  menu.append(input,list,hint);box.append(trigger,menu);field.append(label,box);oldLabel.replaceWith(field);select.hidden=true;select.tabIndex=-1;field.append(select);
  function close(focus=false){menu.hidden=true;trigger.setAttribute('aria-expanded','false');if(focus)trigger.focus();}
  function sync(){value.textContent=select.selectedOptions[0]?.textContent||'全部';}
  function render(){
    list.replaceChildren();const query=input.value.trim();
    for(const option of select.options){
      if(query&&!option.textContent.includes(query))continue;
      const button=document.createElement('button');button.type='button';button.className='dropdown-option';button.textContent=option.textContent;
      button.setAttribute('aria-pressed',String(select.value===option.value));
      button.addEventListener('click',()=>{select.value=option.value;sync();close(true);select.dispatchEvent(new Event('change',{bubbles:true}));});list.append(button);
    }
    if(!list.children.length){const empty=document.createElement('p');empty.className='dropdown-empty';empty.textContent='没有匹配选项';list.append(empty);}
  }
  function open(){filterDropdowns.forEach(d=>d.close());input.value='';render();menu.hidden=false;trigger.setAttribute('aria-expanded','true');input.focus();}
  trigger.addEventListener('click',()=>menu.hidden?open():close());
  trigger.addEventListener('keydown',e=>{if(e.key==='ArrowDown'){e.preventDefault();open();}});
  input.addEventListener('input',render);
  menu.addEventListener('keydown',e=>{
    if(e.key==='Escape'){e.preventDefault();close(true);return;}
    const buttons=[...list.querySelectorAll('button')],i=buttons.indexOf(document.activeElement);
    if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();buttons[Math.max(0,Math.min(buttons.length-1,i+(e.key==='ArrowDown'?1:-1)))]?.focus();}
    if(e.key==='Enter'&&e.target===input){e.preventDefault();buttons[0]?.click();}
  });
  field.addEventListener('focusout',e=>{if(e.relatedTarget&&!field.contains(e.relatedTarget))close();});
  document.addEventListener('click',e=>{if(!field.contains(e.target))close();});
  select.addEventListener('change',sync);new MutationObserver(sync).observe(select,{childList:true,subtree:true});
  filterDropdowns.push({sync,close});sync();
}
window.syncFilterDropdowns=()=>filterDropdowns.forEach(d=>{d.sync();d.close();});
window.addEventListener('hashchange',()=>window.syncFilterDropdowns());
