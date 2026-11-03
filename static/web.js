/* arXiv Reader 网页：顶栏浮起、设置（范围、摘要、主题）、搜索、收藏抽屉、日历、目录 */
(function () {
  "use strict";

  var PREFS_KEY = "arxiv_reader_prefs_v2";
  var CART_KEY = "arxiv_reader_paper_cart_v1"; // 和旧版页面同一个 key，以前收藏的论文还在
  var DEFAULTS = { mode: "auto", abs: "both", scope: "primary" };
  var root = document.documentElement;
  var $ = function (id) { return document.getElementById(id); };
  var all = function (sel, el) { return Array.prototype.slice.call((el || document).querySelectorAll(sel)); };
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function load(key, fallback) {
    try { var raw = localStorage.getItem(key); return raw ? JSON.parse(raw) : fallback; } catch (e) { return fallback; }
  }
  function save(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
  }

  /* ---------- 顶栏：离开顶部以后浮起来 ---------- */
  var header = document.querySelector("header.top");
  var rafTop = 0;
  function onScrollTop() { rafTop = 0; header.classList.toggle("not-top", window.scrollY > 20); }
  window.addEventListener("scroll", function () { if (!rafTop) rafTop = requestAnimationFrame(onScrollTop); }, { passive: true });
  onScrollTop();

  /* ---------- 提示 ---------- */
  var toastEl = $("toast");
  var toastTimer = 0;
  function toast(text) {
    toastEl.textContent = text;
    toastEl.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove("show"); }, 1600);
  }

  /* ---------- 弹出的小框（设置、日历）：点按钮开关，点外面或按 Esc 收起 ---------- */
  var pops = [];
  function popup(btn, pop, onOpen) {
    function place() {
      var r = btn.getBoundingClientRect();
      pop.style.top = Math.round(r.bottom + 10) + "px";
      var left = pop.dataset.align === "left" ? r.left : r.right - pop.offsetWidth;
      pop.style.left = Math.max(12, Math.min(Math.round(left), window.innerWidth - pop.offsetWidth - 12)) + "px";
    }
    var item = {
      close: function () { pop.classList.remove("on"); btn.classList.remove("on"); },
      isOpen: function () { return pop.classList.contains("on"); },
      place: place
    };
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = !item.isOpen();
      pops.forEach(function (x) { x.close(); });
      if (!open) return;
      if (onOpen) onOpen();
      pop.classList.add("on");
      btn.classList.add("on");
      place();
    });
    pop.addEventListener("click", function (e) { e.stopPropagation(); });
    pops.push(item);
    return item;
  }
  document.addEventListener("click", function () { pops.forEach(function (x) { x.close(); }); });
  window.addEventListener("resize", function () { pops.forEach(function (x) { if (x.isOpen()) x.place(); }); });

  /* ---------- 设置 ---------- */
  var prefs = Object.assign({}, DEFAULTS, load(PREFS_KEY, {}) || {});
  var onPrefs = [];
  function applyPrefs() {
    root.setAttribute("data-mode", prefs.mode);
    root.setAttribute("data-abs", prefs.abs);
    root.setAttribute("data-scope", prefs.scope);
    all(".seg[data-pref]").forEach(function (seg) {
      all("button", seg).forEach(function (b) { b.classList.toggle("on", b.dataset.v === prefs[seg.dataset.pref]); });
    });
    onPrefs.forEach(function (fn) { fn(); });
  }
  all(".seg[data-pref] button").forEach(function (b) {
    b.addEventListener("click", function () {
      prefs[b.parentNode.dataset.pref] = b.dataset.v;
      save(PREFS_KEY, prefs);
      applyPrefs();
    });
  });
  popup($("setBtn"), $("setPop"));

  /* ---------- 收藏 ---------- */
  var badge = $("cartBadge");
  var drawer = $("cartDrawer");
  var mask = $("cartMask");
  var list = $("cartList");
  function icon(name) { return $("icons").content.querySelector('[data-ic="' + name + '"]').innerHTML; }
  var xIcon = icon("x");
  var pageDate = ($("daily") && $("daily").dataset.date) || "";

  function normalize(items) {
    if (!Array.isArray(items)) return [];
    var seen = {};
    return items.filter(function (x) {
      if (!x || typeof x.id !== "string" || !x.id.trim() || seen[x.id]) return false;
      seen[x.id] = true;
      return true;
    }).map(function (x) {
      return { id: x.id.trim(), title: x.title || "", date: x.date || "", category: x.category || "", added_at: x.added_at || "" };
    });
  }
  var cart = normalize(load(CART_KEY, []));
  var has = function (id) { return cart.some(function (x) { return x.id === id; }); };

  function renderCart() {
    badge.hidden = cart.length === 0;
    badge.textContent = String(cart.length);
    $("cartCount").textContent = String(cart.length);
    list.innerHTML = "";
    cart.slice().reverse().forEach(function (x) {
      var row = document.createElement("div");
      row.className = "citem";
      var body = document.createElement("div");
      body.className = "body";
      var t = document.createElement("a");
      t.className = "t";
      t.href = "https://arxiv.org/abs/" + x.id;
      t.target = "_blank";
      t.rel = "noopener";
      t.textContent = x.title || x.id;
      var m = document.createElement("div");
      m.className = "m";
      m.textContent = x.id + (x.date ? " · " + x.date : "");
      body.appendChild(t);
      body.appendChild(m);
      var del = document.createElement("button");
      del.type = "button";
      del.className = "x";
      del.dataset.del = x.id;
      del.setAttribute("aria-label", "移除");
      del.innerHTML = xIcon;
      row.appendChild(body);
      row.appendChild(del);
      list.appendChild(row);
    });
    all(".star").forEach(function (b) {
      var on = has(b.dataset.id);
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }
  function setCart(next) { cart = next; save(CART_KEY, cart); renderCart(); }

  function openDrawer(open) {
    drawer.classList.toggle("on", open);
    mask.classList.toggle("on", open);
    root.classList.toggle("lock", open && window.matchMedia("(max-width: 760px)").matches);
  }
  $("cartBtn").addEventListener("click", function (e) {
    e.stopPropagation();
    pops.forEach(function (x) { x.close(); });
    openDrawer(!drawer.classList.contains("on"));
  });
  $("cartClose").addEventListener("click", function () { openDrawer(false); });
  mask.addEventListener("click", function () { openDrawer(false); });

  function copy(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise(function (resolve, reject) {
      var a = document.createElement("textarea");
      a.value = text;
      a.style.position = "fixed";
      a.style.opacity = "0";
      document.body.appendChild(a);
      a.select();
      try { document.execCommand("copy") ? resolve() : reject(); } catch (err) { reject(err); }
      document.body.removeChild(a);
    });
  }
  function copyCart(withTitle) {
    if (!cart.length) return;
    var text = cart.map(function (x) { return withTitle && x.title ? x.id + "  " + x.title : x.id; }).join("\n");
    copy(text).then(function () { toast("已复制 " + cart.length + " 篇"); }, function () { toast("复制失败"); });
  }
  $("cartCopy").addEventListener("click", function () { copyCart(false); });
  $("cartCopyTitles").addEventListener("click", function () { copyCart(true); });
  $("cartClear").addEventListener("click", function () {
    if (cart.length && window.confirm("清空 " + cart.length + " 篇收藏？")) setCart([]);
  });

  document.addEventListener("click", function (e) {
    var t = e.target instanceof Element ? e.target : null;
    if (!t) return;
    var del = t.closest("[data-del]");
    if (del) { setCart(cart.filter(function (x) { return x.id !== del.dataset.del; })); return; }
    var star = t.closest(".star");
    if (star) {
      var id = star.dataset.id;
      if (has(id)) setCart(cart.filter(function (x) { return x.id !== id; }));
      else setCart(cart.concat([{ id: id, title: star.dataset.title || "", date: pageDate, category: "", added_at: new Date().toISOString() }]));
      return;
    }
    var more = t.closest(".more");
    if (more) { more.closest(".paper").classList.toggle("open"); return; }
    var authors = t.closest(".p-authors");
    if (authors) authors.classList.toggle("open");
  });
  window.addEventListener("storage", function (e) { if (e.key === CART_KEY) { cart = normalize(load(CART_KEY, [])); renderCart(); } });
  renderCart();

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    if (drawer.classList.contains("on")) openDrawer(false);
    pops.forEach(function (x) { x.close(); });
  });

  if (!$("daily")) { applyPrefs(); return; }

  /* ---------- 日历 ---------- */
  var dates = JSON.parse($("dateList").textContent);
  var dateSet = {};
  dates.forEach(function (d) { dateSet[d] = true; });
  var months = [];
  dates.forEach(function (d) { var m = d.slice(0, 7); if (months.indexOf(m) < 0) months.push(m); });
  months.sort();
  var calPop = $("calPop");
  calPop.dataset.align = "left";
  var shown = pageDate.slice(0, 7);
  var leftIcon = icon("left");
  var rightIcon = icon("right");

  function renderCal() {
    var y = +shown.slice(0, 4);
    var m = +shown.slice(5, 7);
    var k = months.indexOf(shown);
    var html = '<div class="pk-head"><span class="ttl">' + y + " 年 " + m + " 月</span>" +
      '<button type="button" class="pk-nav" data-step="-1" aria-label="上个月"' + (k <= 0 ? " disabled" : "") + ">" + leftIcon + "</button>" +
      '<button type="button" class="pk-nav" data-step="1" aria-label="下个月"' + (k >= months.length - 1 ? " disabled" : "") + ">" + rightIcon + "</button></div>" +
      '<div class="pk-grid">' + ["一", "二", "三", "四", "五", "六", "日"].map(function (w) { return '<span class="pk-dow">' + w + "</span>"; }).join("");
    var first = new Date(y, m - 1, 1);
    var pad = (first.getDay() + 6) % 7;
    for (var i = 0; i < pad; i++) html += "<span></span>";
    var days = new Date(y, m, 0).getDate();
    for (var d = 1; d <= days; d++) {
      var iso = shown + "-" + (d < 10 ? "0" + d : d);
      if (iso === pageDate) html += '<span class="pk-day sel">' + d + "</span>";
      else if (dateSet[iso]) html += '<a class="pk-day" href="/daily/' + iso + '">' + d + "</a>";
      else html += '<span class="pk-day out">' + d + "</span>";
    }
    calPop.innerHTML = html + "</div>";
  }
  calPop.addEventListener("click", function (e) {
    var nav = e.target instanceof Element ? e.target.closest(".pk-nav") : null;
    if (!nav || nav.disabled) return;
    var k = months.indexOf(shown) + Number(nav.dataset.step);
    if (k >= 0 && k < months.length) { shown = months[k]; renderCal(); }
  });
  popup($("dateBtn"), calPop, function () { shown = pageDate.slice(0, 7); renderCal(); });

  /* ---------- 搜索、范围和每块的篇数 ---------- */
  var box = $("searchBox");
  var input = $("searchInput");
  var count = $("searchCount");
  var cards = all(".paper");
  var groups = all(".group");
  var texts = new WeakMap();
  var timer = 0;

  function textOf(card) {
    var t = texts.get(card);
    if (t === undefined) { t = card.textContent.replace(/\s+/g, " ").toLowerCase(); texts.set(card, t); }
    return t;
  }
  function inScope(group) {
    var cross = /-cross$/.test(group.dataset.group);
    return prefs.scope === "all" || (prefs.scope === "cross") === cross;
  }
  function refresh() {
    var terms = input.value.toLowerCase().split(/\s+/).filter(Boolean);
    var total = 0;
    groups.forEach(function (g) {
      var n = 0;
      all(".paper", g).forEach(function (card) {
        var ok = terms.every(function (term) { return textOf(card).indexOf(term) >= 0; });
        card.hidden = !ok;
        if (ok) n += 1;
      });
      all('[data-count="' + g.dataset.group + '"]').forEach(function (el) { el.textContent = String(n); });
      g.dataset.n = String(n);
      if (inScope(g)) total += n;
    });
    count.textContent = terms.length ? total + " 篇" : "";
    buildToc();
  }
  input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(refresh, 120); });
  function openSearch(open) {
    box.classList.toggle("open", open);
    $("searchBtn").classList.toggle("on", open);
    if (open) input.focus();
    else if (input.value) { input.value = ""; refresh(); }
  }
  $("searchBtn").addEventListener("click", function (e) { e.stopPropagation(); openSearch(!box.classList.contains("open")); });
  input.addEventListener("keydown", function (e) { if (e.key === "Escape") { e.stopPropagation(); openSearch(false); } });
  document.addEventListener("keydown", function (e) {
    var tag = (e.target && e.target.tagName) || "";
    if (e.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA") { e.preventDefault(); openSearch(true); }
  });

  /* ---------- 目录：每个分类一项；范围是“全部”时，下面再列它的 cross-list。跟着滚动标出看到的那一项 ---------- */
  var tocList = $("tocList");
  var ind = $("tocInd");
  var targets = [];
  var links = [];
  var locked = false;
  var pinned = -1; // 点过的那一项：页面滚不到它（比如最后几块很短）时也一直标着它，离开落点 40px 以后才放开
  var pinnedY = 0;

  function groupCount(section, kind) {
    var g = section.querySelector('.group[data-group$="-' + kind + '"]');
    return g ? +(g.dataset.n || all(".paper", g).length) : 0;
  }
  function buildToc() {
    pinned = -1;
    all("a", tocList).forEach(function (a) { a.remove(); });
    targets = [];
    links = [];
    all(".cat", $("daily")).forEach(function (section) {
      var main = prefs.scope === "cross" ? "cross" : "new";
      add(section, section.dataset.code, groupCount(section, main), false);
      var sub = section.querySelector(".sub");
      if (prefs.scope === "all" && sub) add(sub, "cross-list", groupCount(section, "cross"), true);
    });
    spy();
  }
  function add(target, label, n, lv2) {
    var a = document.createElement("a");
    a.href = "#" + target.id;
    if (lv2) a.className = "lv2";
    var l = document.createElement("span");
    l.textContent = label;
    var c = document.createElement("span");
    c.className = "n";
    c.textContent = String(n);
    a.appendChild(l);
    a.appendChild(c);
    var k = targets.length;
    a.addEventListener("click", function (e) { e.preventDefault(); jump(k); });
    tocList.appendChild(a);
    targets.push(target);
    links.push(a);
  }
  function mark(k) {
    links.forEach(function (a, n) { a.classList.toggle("on", n === k); });
    var a = links[k];
    if (!a) return;
    ind.style.transform = "translateY(" + a.offsetTop + "px)";
    ind.style.height = a.offsetHeight + "px";
  }
  // 看到哪一项：顶边已经过了顶栏下面那条线的最后一项；滚到底就算最后一项
  function spy() {
    if (locked || !links.length) return;
    if (pinned >= 0 && Math.abs(window.scrollY - pinnedY) < 40) { mark(pinned); return; }
    pinned = -1;
    var line = 110;
    var k = 0;
    targets.forEach(function (el, n) { if (el.getBoundingClientRect().top <= line) k = n; });
    if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) k = targets.length - 1;
    mark(k);
  }
  function jump(k) {
    mark(k);
    pinned = k;
    locked = true;
    var done = function () { locked = false; pinnedY = window.scrollY; window.removeEventListener("scrollend", done); spy(); };
    window.addEventListener("scrollend", done);
    setTimeout(done, reduced ? 50 : 1500);
    targets[k].scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
    history.replaceState(null, "", "#" + targets[k].id);
  }
  var rafSpy = 0;
  window.addEventListener("scroll", function () { if (!rafSpy) rafSpy = requestAnimationFrame(function () { rafSpy = 0; spy(); }); }, { passive: true });
  window.addEventListener("resize", spy);

  onPrefs.push(refresh);
  applyPrefs();
})();
