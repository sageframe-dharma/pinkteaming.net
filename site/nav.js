/* ════════════════════════════════════════════════════════════════
   Nav object — four-armed draggable navigation, shared across all
   pinkteaming.net pages. Auto-mounts on load. Per-page identity is
   set via <html data-page="surface|text|practice|reading">.

   Pairs with nav.css. Each page just needs:
     <link rel="stylesheet" href="nav.css">
     <script src="nav.js" defer></script>

   The visualization (formerly the root) now lives at /surface/. The
   site root is a gateway page that drives the morph animation via
   the public window.NavObject.navigate(id) API exposed below.
   ════════════════════════════════════════════════════════════════ */
(function () {
  const ROUTES = {
    surface:  '/surface',
    text:     '/manifesto',
    practice: '/practice',
    reading:  '/reading',
  };

  const DESTINATIONS = [
    { id: 'surface',  label: 'SURFACE',  baseAngle: 295, restRank: 0 },
    { id: 'text',     label: 'TEXT',     baseAngle: 30,  restRank: 1 },
    { id: 'reading',  label: 'READING',  baseAngle: 220, restRank: 2 },
    { id: 'practice', label: 'PRACTICE', baseAngle: 130, restRank: 3 },
  ];
  const ANGLE_JITTER = 22;
  const MIN_ANGULAR_SEP = 55;
  const RANK_LENGTHS = [0.50, 0.36, 0.26, 0.16];

  const STORAGE_KEY = 'pt.navobject.v1';

  // Resolve the active arm. Priority: <html data-page="...">, then
  // pathname match, then default 'surface'.
  function resolvePageId() {
    const ds = (document.documentElement.dataset.page || '').toLowerCase();
    if (DESTINATIONS.find(d => d.id === ds)) return ds;
    const path = window.location.pathname.replace(/\.html$/, '').replace(/\/$/, '');
    if (path.endsWith('/surface') || path.endsWith('/door')) return 'surface';
    if (path.endsWith('/manifesto') || path.endsWith('/text')) return 'text';
    if (path.endsWith('/practice')) return 'practice';
    if (path.endsWith('/reading')) return 'reading';
    // Root (the gateway) — start with the visitor "on" surface; the gateway
    // script then morphs to the destination arm before redirecting.
    return 'surface';
  }

  // ── Auto-mount the nav DOM ─────────────────────────────
  const navEl = document.createElement('div');
  navEl.className = 'nav-object';
  navEl.id = 'navObject';
  navEl.setAttribute('role', 'navigation');
  navEl.setAttribute('aria-label', 'Site navigation');
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const svgEl = document.createElementNS(SVG_NS, 'svg');
  svgEl.setAttribute('viewBox', '-60 -60 300 300');
  svgEl.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  navEl.appendChild(svgEl);
  document.body.appendChild(navEl);

  // (Removed hamburger — star nav works on mobile too via touch handlers below.)

  let active = resolvePageId();

  // ── Geometry ──────────────────────────────────────────
  const SIZE = 180;
  const CENTER = SIZE / 2;
  const VALLEY_FRAC = 0.085;

  function armEndpoint(angleDeg, lengthFrac) {
    const r = lengthFrac * SIZE;
    const rad = (angleDeg * Math.PI) / 180;
    return { x: CENTER + Math.cos(rad) * r, y: CENTER + Math.sin(rad) * r };
  }

  const angleState = {};
  DESTINATIONS.forEach(d => { angleState[d.id] = d.baseAngle; });

  function angDist(a, b) {
    return Math.abs(((a - b) % 360 + 540) % 360 - 180);
  }
  function rollAngles() {
    for (let attempt = 0; attempt < 60; attempt++) {
      const next = {};
      DESTINATIONS.forEach(d => {
        const j = (Math.random() * 2 - 1) * ANGLE_JITTER;
        next[d.id] = (d.baseAngle + j + 360) % 360;
      });
      let ok = true;
      const ids = DESTINATIONS.map(d => d.id);
      for (let i = 0; i < ids.length && ok; i++) {
        for (let k = i + 1; k < ids.length && ok; k++) {
          if (angDist(next[ids[i]], next[ids[k]]) < MIN_ANGULAR_SEP) ok = false;
        }
      }
      if (ok) return next;
    }
    const out = {};
    DESTINATIONS.forEach(d => { out[d.id] = d.baseAngle; });
    return out;
  }

  function getOrderedDests() {
    return DESTINATIONS.slice().sort((a, b) => angleState[a.id] - angleState[b.id]);
  }

  function valleyAngle(a, b) {
    let mid = (a + b) / 2;
    if (b < a) mid = ((a + b + 360) / 2) % 360;
    const jitter = ((Math.sin(a * 12.9898 + b * 78.233) * 43758.5453) % 1) * 8 - 4;
    return (mid + jitter + 360) % 360;
  }

  // ── SVG nodes ─────────────────────────────────────────
  const starPoly = document.createElementNS(SVG_NS, 'polygon');
  starPoly.classList.add('star-poly');
  svgEl.appendChild(starPoly);

  const centerDot = document.createElementNS(SVG_NS, 'circle');
  centerDot.classList.add('center-dot');
  centerDot.setAttribute('cx', CENTER);
  centerDot.setAttribute('cy', CENTER);
  centerDot.setAttribute('r', 1.6);
  svgEl.appendChild(centerDot);

  // Invisible click target around the center dot — re-rolls arm angles.
  const centerHit = document.createElementNS(SVG_NS, 'circle');
  centerHit.classList.add('center-hit');
  centerHit.setAttribute('cx', CENTER);
  centerHit.setAttribute('cy', CENTER);
  centerHit.setAttribute('r', 14);
  centerHit.addEventListener('click', (e) => {
    e.stopPropagation();
    if (justDragged) return;
    reroll();
  });
  svgEl.appendChild(centerHit);

  DESTINATIONS.forEach((d) => {
    const g = document.createElementNS(SVG_NS, 'g');
    g.setAttribute('data-id', d.id);

    const labelBg = document.createElementNS(SVG_NS, 'rect');
    labelBg.classList.add('label-bg');
    g.appendChild(labelBg);

    const label = document.createElementNS(SVG_NS, 'text');
    label.classList.add('arm-label');
    label.textContent = d.label;
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('dominant-baseline', 'middle');
    g.appendChild(label);

    const hit = document.createElementNS(SVG_NS, 'circle');
    hit.classList.add('arm-hit');
    hit.setAttribute('r', 24);
    g.appendChild(hit);

    g.__labelBg = labelBg;
    g.__label = label;
    g.__hit = hit;

    g.addEventListener('click', (e) => {
      e.stopPropagation();
      if (justDragged) return;
      navigateTo(d.id);
    });
    // Mobile/touch: fire on touchend so iOS Safari doesn't eat the click.
    g.addEventListener('touchend', (e) => {
      if (justDragged) return;
      e.preventDefault();
      e.stopPropagation();
      navigateTo(d.id);
    }, { passive: false });

    svgEl.appendChild(g);
    d.__group = g;
  });

  function targetLengthFor(destId, activeId) {
    if (destId === activeId) return RANK_LENGTHS[0];
    const others = DESTINATIONS
      .filter(d => d.id !== activeId)
      .sort((a, b) => a.restRank - b.restRank);
    const idx = others.findIndex(d => d.id === destId);
    return RANK_LENGTHS[idx + 1];
  }

  const armState = {};
  DESTINATIONS.forEach(d => { armState[d.id] = targetLengthFor(d.id, active); });

  function paintArms() {
    const ordered = getOrderedDests();
    const pts = [];
    ordered.forEach((d, i) => {
      const ang = angleState[d.id];
      const tip = armEndpoint(ang, armState[d.id]);
      pts.push(tip.x.toFixed(2) + ',' + tip.y.toFixed(2));
      const next = ordered[(i + 1) % ordered.length];
      const va = valleyAngle(ang, angleState[next.id]);
      const valley = armEndpoint(va, VALLEY_FRAC);
      pts.push(valley.x.toFixed(2) + ',' + valley.y.toFixed(2));
    });
    starPoly.setAttribute('points', pts.join(' '));
    starPoly.classList.toggle('has-active', !!active);

    DESTINATIONS.forEach((d) => {
      const isActive = (d.id === active);
      const frac = armState[d.id];
      const ang = angleState[d.id];
      const labelTip = armEndpoint(ang, frac + 14 / SIZE);
      const label = d.__group.__label;
      label.setAttribute('x', labelTip.x);
      label.setAttribute('y', labelTip.y);

      const cx = Math.cos(ang * Math.PI / 180);
      let anchor = 'middle';
      if (cx > 0.35) anchor = 'start';
      else if (cx < -0.35) anchor = 'end';
      label.setAttribute('text-anchor', anchor);
      label.classList.toggle('active', isActive);

      const labelBg = d.__group.__labelBg;
      const fontPx = parseFloat(getCss('--nav-label-size')) * 16;
      const charAdvance = fontPx * 0.68;
      const textW = d.label.length * charAdvance;
      const textH = fontPx * 1.05;
      const padX = 5, padY = 2.5;

      let bgX;
      if (anchor === 'start')      bgX = labelTip.x;
      else if (anchor === 'end')   bgX = labelTip.x - textW;
      else                         bgX = labelTip.x - textW / 2;
      const bgY = labelTip.y - textH / 2;

      labelBg.setAttribute('x', bgX - padX);
      labelBg.setAttribute('y', bgY - padY);
      labelBg.setAttribute('width',  textW + padX * 2);
      labelBg.setAttribute('height', textH + padY * 2);

      const hitTip = armEndpoint(ang, Math.max(frac, RANK_LENGTHS[1]) * 0.7 + 0.1);
      d.__group.__hit.setAttribute('cx', hitTip.x);
      d.__group.__hit.setAttribute('cy', hitTip.y);
    });
  }

  function easeInOut(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }

  let animRaf = null;
  function animateArms(prevActive, nextActive, duration, delayForGrow, nextAngles) {
    const start = performance.now();
    const startLen = Object.assign({}, armState);
    const startAng = Object.assign({}, angleState);
    const deltaAng = {};
    DESTINATIONS.forEach(d => {
      let diff = ((nextAngles[d.id] - startAng[d.id]) + 540) % 360 - 180;
      deltaAng[d.id] = diff;
    });

    function frame(now) {
      const t = Math.min(1, (now - start) / duration);
      const e = easeInOut(t);
      DESTINATIONS.forEach((d) => {
        const targetLen = targetLengthFor(d.id, nextActive);
        if (d.id === nextActive) {
          const tg = Math.min(1, Math.max(0, (now - start - delayForGrow) / (duration - delayForGrow)));
          const eg = easeInOut(tg);
          armState[d.id] = startLen[d.id] + (targetLen - startLen[d.id]) * eg;
        } else {
          armState[d.id] = startLen[d.id] + (targetLen - startLen[d.id]) * e;
        }
        angleState[d.id] = (startAng[d.id] + deltaAng[d.id] * e + 360) % 360;
      });
      paintArms();
      if (t < 1) animRaf = requestAnimationFrame(frame);
      else animRaf = null;
    }
    if (animRaf) cancelAnimationFrame(animRaf);
    animRaf = requestAnimationFrame(frame);
  }

  function renderArms(rollInitial) {
    if (rollInitial) {
      const a = rollAngles();
      DESTINATIONS.forEach(d => { angleState[d.id] = a[d.id]; });
    }
    DESTINATIONS.forEach(d => { armState[d.id] = targetLengthFor(d.id, active); });
    paintArms();
  }

  function getCss(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  let navigating = false;
  function navigateTo(id, opts) {
    if (navigating || id === active) return;
    opts = opts || {};
    navigating = true;
    active = id;
    DESTINATIONS.forEach(d => {
      d.__group.__label.classList.toggle('active', d.id === active);
    });

    const dur = parseInt(getCss('--nav-transition-duration')) || 400;
    // The gateway page passes keepAngles:true so the morph only changes
    // arm lengths, not orientation — avoids the visible angular shuffle
    // when the morph is intentionally slow (e.g. 2.5s on the gateway).
    const nextAngles = opts.keepAngles
      ? Object.assign({}, angleState)
      : rollAngles();
    animateArms(null, id, dur, 50, nextAngles);

    setTimeout(() => {
      navEl.dispatchEvent(new CustomEvent('navobject:navigate', {
        bubbles: true,
        detail: { id }
      }));
      navigating = false;
      saveState({ active, ...readPos() });
    }, dur + 50);
  }

  // Re-roll arm angles without changing the active destination.
  let rerolling = false;
  function reroll() {
    if (rerolling || navigating) return;
    rerolling = true;
    const dur = parseInt(getCss('--nav-transition-duration')) || 400;
    const nextAngles = rollAngles();
    animateArms(null, active, dur, 0, nextAngles);
    setTimeout(() => {
      rerolling = false;
      saveState({ active, ...readPos() });
    }, dur + 50);
  }

  function readPos() {
    const r = navEl.getBoundingClientRect();
    return { x: r.left, y: r.top };
  }

  // ── Drag (viewport-bounded) ─────────────────────────────
  let dragging = false;
  let justDragged = false;
  let dragStart = null;
  let posStart = null;
  const MARGIN = 24;
  // Default position when nothing is in localStorage: dot center is anchored
  // to the bottom-right corner of the .surface-band (the white reading strip's
  // lower rule, at the right viewport edge). DOT_RIGHT is px left of that
  // corner; DOT_ABOVE_SURFACE is px above the surface band's bottom line.
  // Anchoring to the surface band keeps the dot at a fixed visual offset from
  // the reading strip across viewport heights, instead of drifting with the
  // top edge. Wrapper is var(--nav-container-size) = 220px square; dot sits at
  // wrapper center, so wrapper top-left = (dotX - 110, dotY - 110).
  // Pages without a .surface-band fall back to the legacy upper-right anchor.
  const DEFAULT_DOT_RIGHT         = 140;
  const DEFAULT_DOT_ABOVE_SURFACE = 280;
  const FALLBACK_DOT_TOP          = 175;

  function setPos(x, y) {
    navEl.style.left = x + 'px';
    navEl.style.top  = y + 'px';
    navEl.style.right = 'auto';
  }

  function clampToViewport(x, y, animate) {
    const w = navEl.offsetWidth;
    const h = navEl.offsetHeight;
    const maxX = window.innerWidth - w;
    const maxY = window.innerHeight - h;
    const cx = Math.max(0, Math.min(maxX, x));
    const cy = Math.max(0, Math.min(maxY, y));
    if (animate && (cx !== x || cy !== y)) {
      navEl.classList.add('snapping');
      setPos(cx, cy);
      setTimeout(() => navEl.classList.remove('snapping'), 220);
    } else {
      setPos(cx, cy);
    }
    return { x: cx, y: cy };
  }

  navEl.addEventListener('mousedown', (e) => {
    if (e.target.classList && (e.target.classList.contains('arm-hit') || e.target.classList.contains('center-hit'))) return;
    dragging = true;
    justDragged = false;
    const r = navEl.getBoundingClientRect();
    dragStart = { x: e.clientX, y: e.clientY };
    posStart = { x: r.left, y: r.top };
    navEl.classList.add('dragging');
    e.preventDefault();
  });

  window.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const dx = e.clientX - dragStart.x;
    const dy = e.clientY - dragStart.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) justDragged = true;
    setPos(posStart.x + dx, posStart.y + dy);
  });

  window.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    navEl.classList.remove('dragging');
    const r = navEl.getBoundingClientRect();
    const final = clampToViewport(r.left, r.top, true);
    saveState({ active, x: final.x, y: final.y });
    setTimeout(() => { justDragged = false; }, 50);
  });

  // ── Persistence ───────────────────────────────────────
  function loadState() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; }
    catch (_) { return {}; }
  }
  function saveState(s) {
    try {
      // Persist current arm orientations alongside position/active. This
      // lets the next page render the star at the same angles the user
      // last saw — no re-roll snap on page load. Without this, a slow
      // morph (gateway → manifesto) would visibly re-shuffle on arrival.
      const payload = Object.assign({}, s, {
        angles: Object.assign({}, angleState),
      });
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch (_) {}
  }

  // ── Routing ───────────────────────────────────────────
  navEl.addEventListener('navobject:navigate', (e) => {
    const id = e.detail && e.detail.id;
    const url = ROUTES[id];
    if (url) window.location.href = url;
  });

  // ── Init ──────────────────────────────────────────────
  function init() {
    const saved = loadState();

    // Restore arm angles if a prior page saved them. This is what makes
    // a slow gateway morph land cleanly on /manifesto/ — same orientation,
    // no re-shuffle. First-ever visit (no saved angles) still rolls fresh.
    let hasSavedAngles = false;
    if (saved.angles && typeof saved.angles === 'object') {
      hasSavedAngles = DESTINATIONS.every(d => typeof saved.angles[d.id] === 'number');
      if (hasSavedAngles) {
        DESTINATIONS.forEach(d => { angleState[d.id] = saved.angles[d.id]; });
      }
    }

    if (typeof saved.x === 'number' && typeof saved.y === 'number') {
      const c = clampToViewport(saved.x, saved.y, false);
      saveState({ active, x: c.x, y: c.y });
    } else {
      const halfW = navEl.offsetWidth  / 2;
      const halfH = navEl.offsetHeight / 2;
      const surface = document.querySelector('.surface-band');
      let dotX, dotY;
      if (surface) {
        const r = surface.getBoundingClientRect();
        dotX = r.right - DEFAULT_DOT_RIGHT;
        dotY = r.bottom - DEFAULT_DOT_ABOVE_SURFACE;
      } else {
        dotX = window.innerWidth - DEFAULT_DOT_RIGHT;
        dotY = FALLBACK_DOT_TOP;
      }
      setPos(dotX - halfW, dotY - halfH);
    }
    renderArms(!hasSavedAngles);
  }

  window.addEventListener('resize', () => {
    const r = navEl.getBoundingClientRect();
    clampToViewport(r.left, r.top, true);
  });

  // Public API — the gateway page (/) uses this to programmatically
  // morph the star from SURFACE to TEXT before redirecting.
  window.NavObject = {
    navigate: navigateTo,
    reroll: reroll,
    getActive: () => active,
    el: navEl,
  };

  init();
})();
