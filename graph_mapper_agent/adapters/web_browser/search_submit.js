(payload) => {
  const normalize = value => (value || '').replace(/\s+/g, ' ').trim();
  const lower = value => normalize(value).toLowerCase();

  const visible = el => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (!style) return false;
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    if (style.opacity === '0') return false;
    const rect = el.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return false;
    return true;
  };

  const labelTextFor = el => {
    if (!el) return '';
    const ariaLabel = normalize(el.getAttribute('aria-label') || '');
    if (ariaLabel) return ariaLabel;

    const idAttr = normalize(el.getAttribute('id') || '');
    if (idAttr) {
      try {
        const forLabel = document.querySelector(`label[for="${CSS.escape(idAttr)}"]`);
        const txt = normalize(forLabel ? (forLabel.innerText || forLabel.textContent || '') : '');
        if (txt) return txt;
      } catch (_) {}
    }

    const parentLabel = el.closest('label');
    const parentTxt = normalize(parentLabel ? (parentLabel.innerText || parentLabel.textContent || '') : '');
    if (parentTxt) return parentTxt;

    return '';
  };

  const target = payload.target || {};
  const query = String(payload.query_text || '').trim();
  if (!query) {
    return { ok: false, reason: 'empty_query_text' };
  }

  const candidates = Array.from(document.querySelectorAll('input, textarea'));
  let best = null;

  for (const el of candidates) {
    if (!visible(el)) continue;

    const type = lower(el.getAttribute('type') || 'text');
    if (['password', 'email', 'hidden', 'file', 'checkbox', 'radio'].includes(type)) {
      continue;
    }

    const name = normalize(el.getAttribute('name') || '');
    const idAttr = normalize(el.getAttribute('id') || '');
    const placeholder = normalize(el.getAttribute('placeholder') || '');
    const ariaLabel = normalize(el.getAttribute('aria-label') || '');
    const label = labelTextFor(el);
    const form = el.closest('form');
    const formAction = normalize(form ? (form.getAttribute('action') || '') : '');

    let score = 0.0;

    if (target.id_attr && idAttr === target.id_attr) score += 1.2;
    if (target.name && name === target.name) score += 1.0;
    if (target.placeholder && placeholder === target.placeholder) score += 0.9;
    if (target.aria_label && ariaLabel === target.aria_label) score += 0.9;
    if (target.label && label === target.label) score += 0.8;
    if (target.input_type && type === String(target.input_type).toLowerCase()) score += 0.6;
    if (target.form_action && formAction === target.form_action) score += 0.5;

    const haystack = lower([type, name, idAttr, placeholder, ariaLabel, label, formAction].join(' '));
    if (type === 'search') score += 0.45;
    if (haystack.includes('search') || haystack.includes('buscar') || haystack.includes('find')) score += 0.35;
    if (lower(name) === 'q') score += 0.25;

    if (!best || score > best.score) {
      best = {
        el,
        score,
        target: {
          input_type: type,
          name,
          id_attr: idAttr,
          placeholder,
          aria_label: ariaLabel,
          label,
          form_action: formAction,
        },
      };
    }
  }

  if (!best || best.score < 0.45) {
    return { ok: false, reason: 'target_not_found' };
  }

  const el = best.el;
  try { el.focus(); } catch (_) {}

  if ('value' in el) {
    el.value = '';
    el.value = query;
  } else {
    el.textContent = query;
  }

  try { el.dispatchEvent(new Event('input', { bubbles: true })); } catch (_) {}
  try { el.dispatchEvent(new Event('change', { bubbles: true })); } catch (_) {}

  let submitMethod = 'enter';
  const form = el.closest('form');

  if (form) {
    const submitButton =
      form.querySelector('button[type="submit"], input[type="submit"]');

    try {
      if (typeof form.requestSubmit === 'function') {
        if (submitButton) {
          form.requestSubmit(submitButton);
          submitMethod = 'requestSubmit(button)';
        } else {
          form.requestSubmit();
          submitMethod = 'requestSubmit';
        }
      } else if (submitButton && typeof submitButton.click === 'function') {
        submitButton.click();
        submitMethod = 'submitButton.click';
      } else {
        form.submit();
        submitMethod = 'form.submit';
      }
    } catch (_) {
      try {
        el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
        el.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
        el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
        submitMethod = 'keyboard_enter';
      } catch (_) {}
    }
  } else {
    try {
      el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
      el.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
      el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
      submitMethod = 'keyboard_enter';
    } catch (_) {}
  }

  return {
    ok: true,
    submit_method: submitMethod,
    matched_confidence: Math.min(1.0, best.score),
    matched_target: best.target,
  };
}
