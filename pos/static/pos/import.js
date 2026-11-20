(() => {
  const form = document.querySelector('#stock-upload');
  if (!form) return;
  const file = form.querySelector('input[type=file]');
  file.addEventListener('change', () => {
    const files = [...file.files];
    file.setCustomValidity(files.length > 3 || files.reduce((sum, item) => sum + item.size, 0) > 3 * 1024 * 1024
      ? 'Choose up to three screenshots, no more than 3 MB combined.' : '');
  });
  const button = form.querySelector('button[type=submit]');
  const disabled = button.disabled;
  window.addEventListener('pageshow', () => {button.disabled = disabled; button.textContent = 'Extract items'; form.removeAttribute('aria-busy');});
  form.addEventListener('submit', () => {
    button.disabled = true;
    button.textContent = 'Reading your screenshots…';
    form.setAttribute('aria-busy', 'true');
  });
})();
