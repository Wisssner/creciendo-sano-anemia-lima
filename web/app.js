(function () {
  const $ = (id) => document.getElementById(id);
  let establecimientos = [];
  let estSeleccionado = null;
  let step = 1;
  let ultimoResultado = null;
  let ultimoFaltaHierro = false;

  function hoyISO() {
    const d = new Date();
    const p = (n) => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
  }
  const HOY = hoyISO();
  $('fatt').value = HOY;
  $('fnac').max = HOY;
  $('fatt').max = HOY;

  function fechaDe(id) {
    const v = $(id).value;
    return v ? new Date(v + 'T00:00:00') : null;
  }

  // ---------- live computed fields (edad, IMC, peso/mes, talla/mes) ----------
  function numEntrada(id) {
    const v = parseFloat(($(id).value || '').replace(',', '.'));
    return Number.isFinite(v) ? v : null;
  }
  function recalcular() {
    const fnac = fechaDe('fnac');
    const fatt = fechaDe('fatt') || new Date();
    let edadMeses = null;
    if (fnac) {
      edadMeses = Math.max((fatt - fnac) / (1000 * 60 * 60 * 24 * 30.4368), 0);
      $('st-edad').textContent = edadMeses.toFixed(1) + ' m';
    } else {
      $('st-edad').textContent = '—';
    }
    const peso = numEntrada('peso');
    const talla = numEntrada('talla');
    $('st-imc').textContent = peso && talla ? (peso / Math.pow(talla / 100, 2)).toFixed(1) : '—';
    $('st-pm').textContent = peso && edadMeses ? (peso / edadMeses).toFixed(2) : '—';
    $('st-tm').textContent = talla && edadMeses ? (talla / edadMeses).toFixed(2) : '—';
  }
  ['fnac', 'fatt', 'peso', 'talla'].forEach((id) => $(id).addEventListener('input', recalcular));

  // ---------- peso/talla +/- steppers ----------
  document.querySelectorAll('.num-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const inp = $(btn.dataset.target);
      const stepVal = parseFloat(btn.dataset.step);
      const cur = parseFloat(inp.value) || 0;
      let next = Math.round((cur + stepVal) * 10) / 10;
      if (next < 0) next = 0;
      inp.value = next;
      inp.dispatchEvent(new Event('input', { bubbles: true }));
    });
  });

  // ---------- historial toggle ----------
  $('tiene-hist').addEventListener('change', function () {
    $('hist-fields').style.display = this.checked ? 'grid' : 'none';
  });

  // ---------- establecimientos: carga + selección por desplegable ----------
  async function cargarEstablecimientos() {
    const r = await fetch('/establecimientos');
    establecimientos = await r.json();
    if (establecimientos.length) $('prov').value = establecimientos[0].provincia;
    poblarDistritos();
    poblarEstablecimientosSelect();
  }
  function poblarDistritos() {
    const distritos = [...new Set(establecimientos.map((e) => e.distrito))].sort();
    $('dist').innerHTML = '<option value="">Todos los distritos</option>' +
      distritos.map((d) => `<option value="${d}">${d}</option>`).join('');
  }
  function poblarEstablecimientosSelect() {
    const dist = $('dist').value;
    const filtrados = establecimientos
      .filter((e) => !dist || e.distrito === dist)
      .sort((a, b) => a.nombre.localeCompare(b.nombre));
    $('eess_select').innerHTML = '<option value="">Seleccione un establecimiento…</option>' +
      filtrados.map((e) => `<option value="${e.renipress}">${e.nombre} — ${e.distrito}</option>`).join('');
  }
  $('eess_select').addEventListener('change', function () {
    const e = establecimientos.find((x) => x.renipress === this.value);
    estSeleccionado = e || null;
    $('alt').value = e ? e.altura : '';
  });
  $('dist').addEventListener('change', () => {
    estSeleccionado = null;
    $('alt').value = '';
    poblarEstablecimientosSelect();
  });
  cargarEstablecimientos();

  // ---------- help modal ----------
  $('btn-ayuda').addEventListener('click', () => $('modal-ayuda').classList.add('open'));
  $('modal-close').addEventListener('click', () => $('modal-ayuda').classList.remove('open'));
  $('modal-done').addEventListener('click', () => $('modal-ayuda').classList.remove('open'));
  $('modal-ayuda').addEventListener('click', (ev) => { if (ev.target.id === 'modal-ayuda') $('modal-ayuda').classList.remove('open'); });

  // ---------- tabs ----------
  function irATab(nombre) {
    document.querySelectorAll('.tab-btn').forEach((b) => b.classList.toggle('active', b.dataset.tab === nombre));
    document.querySelectorAll('.tab-panel').forEach((p) => p.classList.toggle('active', p.id === 'tab-' + nombre));
  }
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => irATab(btn.dataset.tab));
  });
  $('ir-a-mensaje').addEventListener('click', () => irATab('mensaje'));

  // ---------- paso a paso (sin scroll automático: no se mueve el header) ----------
  function errDe(n) {
    return document.querySelector('.step-panel[data-step="' + n + '"] .err-msg');
  }
  function mostrarError(n, msg) {
    const err = errDe(n);
    err.textContent = msg;
    err.style.display = 'block';
  }
  function validarPaso(n) {
    errDe(n).style.display = 'none';
    if (n === 1) {
      if (!$('fnac').value) { mostrarError(1, 'Seleccione la fecha de nacimiento.'); return false; }
      if (!$('fatt').value) { mostrarError(1, 'Seleccione la fecha del tamizaje.'); return false; }
      if (!numEntrada('peso')) { mostrarError(1, 'Complete el peso.'); return false; }
      if (!numEntrada('talla')) { mostrarError(1, 'Complete la talla.'); return false; }
    }
    if (n === 2) {
      if (!estSeleccionado) { mostrarError(2, 'Seleccione un establecimiento.'); return false; }
    }
    return true;
  }
  function mostrarPaso(n) {
    document.querySelectorAll('.step-panel').forEach((p) => { p.hidden = Number(p.dataset.step) !== n; });
    document.querySelectorAll('.step-pip').forEach((p) => {
      const s = Number(p.dataset.step);
      p.classList.toggle('active', s === n);
      p.classList.toggle('done', s < n);
    });
    step = n;
  }
  document.querySelectorAll('[data-goto]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const target = Number(btn.dataset.goto);
      if (target > step && !validarPaso(step)) return;
      mostrarPaso(target);
    });
  });
  document.querySelectorAll('.step-pip').forEach((pip) => {
    pip.addEventListener('click', () => {
      const target = Number(pip.dataset.step);
      if (target <= step) mostrarPaso(target);
    });
  });

  // ---------- limpiar ----------
  $('btn-limpiar').addEventListener('click', () => {
    $('f').reset();
    $('fatt').value = HOY;
    $('hist-fields').style.display = 'none';
    $('alt').value = '';
    estSeleccionado = null;
    poblarEstablecimientosSelect();
    recalcular();
    $('resultado').style.display = 'none';
    $('placeholder').style.display = 'flex';
    document.querySelectorAll('.err-msg').forEach((e) => { e.style.display = 'none'; });
    mostrarPaso(1);
  });

  // ---------- submit ----------
  $('f').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    if (!validarPaso(1) || !validarPaso(2)) return;

    const peso = numEntrada('peso');
    const talla = numEntrada('talla');
    const tieneHist = $('tiene-hist').checked;
    const body = {
      renipress: estSeleccionado.renipress,
      sexo: $('sexo').value,
      fecha_nacimiento: $('fnac').value,
      fecha_atencion: $('fatt').value,
      peso: peso,
      talla: talla,
      cred: $('p-cred').checked,
      suplementacion: $('p-supl').checked,
      consejeria: $('p-cons').checked,
      sesion: $('p-ses').checked,
      sis: $('p-sis').checked,
      juntos: $('p-juntos').checked,
      qaliwarma: $('p-qali').checked,
      tiene_historial: tieneHist,
      hb_previa: tieneHist ? numEntrada('hb-prev') : null,
      fecha_previa: tieneHist ? ($('f-prev').value || null) : null,
      n_controles: tieneHist ? parseInt($('n-visitas').value || '0', 10) : null,
    };

    const btn = $('btn-calcular');
    btn.disabled = true;
    const originalHtml = btn.innerHTML;
    btn.textContent = 'Calculando…';
    try {
      const r = await fetch('/predecir', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      if (!r.ok) { const err = await r.json(); throw new Error(err.detail || 'Error en la predicción'); }
      const d = await r.json();
      mostrarResultado(d, !$('p-supl').checked);
    } catch (ex) {
      mostrarError(3, ex.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
  });

  function mostrarResultado(d, faltaHierro) {
    $('placeholder').style.display = 'none';
    $('resultado').style.display = 'flex';
    ultimoResultado = d;
    ultimoFaltaHierro = faltaHierro;

    const pct = Math.round(d.probabilidad * 100);
    $('prob-num').textContent = pct;
    $('prob-num2').textContent = pct;
    const alto = d.riesgo_alto;
    const pill = $('pill-riesgo');
    pill.className = 'pill ' + (alto ? 'alto' : 'bajo');
    $('pill-txt').textContent = alto ? 'Prioridad alta: revisar pronto' : 'Prioridad baja: sin señales urgentes';

    // 100-dot grid: pct filled, rest empty, one outlined at the historical average
    const promedio = Math.round(d.prevalencia_promedio * 100);
    $('prom-general').textContent = promedio;
    const dotsEl = $('dots');
    dotsEl.innerHTML = '';
    for (let i = 0; i < 100; i++) {
      const s = document.createElement('span');
      if (i < pct) s.className = 'on';
      if (i === promedio - 1) s.classList.add('avg');
      dotsEl.appendChild(s);
    }

    // factores (real SHAP)
    const list = $('factores-list');
    list.innerHTML = d.factores.map((f) => `
      <div class="factor-row">
        <span class="flabel">${f.label}</span>
        <div class="factor-track"><div class="factor-fill ${f.direccion}" style="width:${Math.round(f.intensidad * 100)}%"></div></div>
        <span class="factor-dir ${f.direccion}">${f.direccion === 'sube' ? 'sube riesgo' : 'baja riesgo'}</span>
      </div>`).join('');

    // qué hacer: personalize by risk level and the iron-supplement step
    $('step-alto').style.display = alto ? 'flex' : 'none';
    $('step-bajo').style.display = alto ? 'none' : 'flex';
    $('step-hierro').style.display = faltaHierro ? 'flex' : 'none';
    $('hacer-intro').textContent = alto
      ? 'Acciones sugeridas para este resultado: prioridad alta.'
      : 'Acciones sugeridas para este resultado: prioridad baja.';
    $('mensaje-intro').textContent = alto
      ? 'Borrador para compartir con la familia — este resultado indica prioridad alta.'
      : 'Borrador para compartir con la familia — este resultado indica prioridad baja.';

    actualizarMensaje();
    irATab('porque');
  }

  // ---------- mensaje para la familia ----------
  function mensajeTexto() {
    if (!ultimoResultado) return '';
    const lugar = estSeleccionado ? estSeleccionado.nombre : 'el establecimiento de salud más cercano';
    if (ultimoResultado.riesgo_alto) {
      return 'Estimada familia:\n\n' +
        'En el control de hoy, el sistema de apoyo que usa la institución identificó una señal de prioridad para revisar pronto la hemoglobina de su hijo o hija.\n\n' +
        'Esto no es un diagnóstico de anemia: es una orientación para decidir a quién conviene atender primero.\n\n' +
        'Se recomienda acudir a ' + lugar + ' en los próximos días para realizar el control de hemoglobina. Si ya tienen un control programado, no es necesario adelantarlo salvo indicación del personal de salud.\n\n' +
        'Quedamos atentos para acompañar lo que necesiten.';
    }
    return 'Estimada familia:\n\n' +
      'En el control de hoy, el sistema de apoyo que usa la institución no encontró señales que requieran una revisión urgente de hemoglobina.\n\n' +
      'Esto no reemplaza los controles de rutina: se recomienda continuar con las visitas de CRED y una alimentación variada en hierro (sangrecita, hígado, bazo, menestras acompañadas de cítricos).\n\n' +
      'Quedamos atentos ante cualquier consulta.';
  }
  function actualizarMensaje() {
    $('msg-familia').value = mensajeTexto();
  }
  $('btn-copiar-msg').addEventListener('click', async () => {
    const ta = $('msg-familia');
    try {
      await navigator.clipboard.writeText(ta.value);
    } catch (e) {
      ta.removeAttribute('readonly');
      ta.select();
      document.execCommand('copy');
      ta.setAttribute('readonly', 'readonly');
    }
    const fb = $('msg-copiado');
    fb.style.display = 'inline';
    setTimeout(() => { fb.style.display = 'none'; }, 1800);
  });
  $('btn-imprimir-msg').addEventListener('click', () => {
    $('print-mensaje').textContent = $('msg-familia').value;
    window.print();
  });

  recalcular();
})();
