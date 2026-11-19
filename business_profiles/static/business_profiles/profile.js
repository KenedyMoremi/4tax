(() => {
  document.querySelectorAll('[data-collection]').forEach(section => {
    section.querySelector('[data-continue]')?.addEventListener('click', () => {
      const next = section.nextElementSibling;
      next?.scrollIntoView({behavior: 'smooth', block: 'start'});
      next?.querySelector('input:not([type=hidden]),select,button')?.focus();
    });
    const prefix = section.dataset.collection;
    const total = section.querySelector(`[name="${prefix}-TOTAL_FORMS"]`);
    const rows = section.querySelector('[data-rows]');
    const prepare = row => {
      const deletion = row.querySelector('[name$="-DELETE"]');
      row.querySelector('[data-delete-control]').hidden = true;
      const remove = row.querySelector('[data-remove-row]');
      remove.hidden = false;
      if (deletion.checked) row.hidden = true;
      remove.addEventListener('click', () => {
        deletion.checked = true;
        row.hidden = true;
        row.querySelectorAll('input:not([name$="-DELETE"]),select,textarea').forEach(input => input.required = false);
      });
    };
    rows.querySelectorAll('[data-row]').forEach(prepare);
    section.querySelector('[data-add-row]').addEventListener('click', () => {
      const index = Number(total.value);
      if (index >= 50) {
        section.querySelector('[data-row-limit]').textContent = 'Save these details before adding more rows (maximum 50 active rows).';
        return;
      }
      const template = section.querySelector('template');
      const holder = document.createElement('template');
      holder.innerHTML = template.innerHTML.replaceAll('__prefix__', String(index));
      const row = holder.content.firstElementChild;
      rows.append(row);
      total.value = index + 1;
      prepare(row);
      row.querySelector('input:not([type="hidden"]),select,textarea')?.focus();
    });
  });
})();
