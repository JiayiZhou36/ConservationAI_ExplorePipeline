'use strict';
const popup=document.createElement('dialog');
const close=document.createElement('button');close.type='button';close.textContent='Close image';
const fullImage=document.createElement('img');fullImage.alt='Enlarged photograph';
popup.append(close,fullImage);document.body.append(popup);
close.addEventListener('click',()=>popup.close());
popup.addEventListener('click',event=>{if(event.target===popup)popup.close();});
document.querySelectorAll('[data-zoom]').forEach(button=>button.addEventListener('click',()=>{
 fullImage.src=button.dataset.zoom;fullImage.alt=button.getAttribute('aria-label');popup.showModal();
}));
// Next requires a rating; Previous can leave an unanswered trial.
document.querySelectorAll('form').forEach(form=>form.addEventListener('submit',event=>{
 if(form.querySelector('input[name="rating"]') && event.submitter?.value!=='previous' && !form.querySelector('input[name="rating"]:checked')){
  event.preventDefault();alert('Please choose a realism rating, or select “I cannot judge,” before continuing.');
 }
}));
