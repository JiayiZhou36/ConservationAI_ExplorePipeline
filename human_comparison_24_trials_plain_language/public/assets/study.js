"use strict";
const pictures = [...document.querySelectorAll('.study-image')];
const button = document.querySelector('#answer-submit');
const status = document.querySelector('#image-status');
function checkImages() {
  if (!button || !pictures.length) return;
  const ready = pictures.every(picture => picture.complete && picture.naturalWidth > 0);
  const failed = pictures.some(picture => picture.complete && picture.naturalWidth === 0);
  button.disabled = !ready;
  status.textContent = ready ? 'The original photograph and both edited images are ready.' : failed ? 'The original photograph or an edited image could not load. Reload this page before answering.' : 'Loading the original photograph and both edited images…';
}
for (const picture of pictures) {
  picture.addEventListener('load', checkImages);
  picture.addEventListener('error', checkImages);
}
checkImages();
