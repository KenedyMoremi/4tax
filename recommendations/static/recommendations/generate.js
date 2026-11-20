(() => {
  const form = document.querySelector('#recommendation-form');
  if (!form) return;
  const button = form.querySelector('button[type=submit]');
  const disabled = button.disabled;
  form.addEventListener('submit', () => {
    button.disabled = true;
    button.textContent = 'Preparing your action plan…';
    form.setAttribute('aria-busy', 'true');
  });
  window.addEventListener('pageshow', () => {
    button.disabled = disabled;
    button.textContent = 'Generate recommendations';
    form.removeAttribute('aria-busy');
  });
})();
