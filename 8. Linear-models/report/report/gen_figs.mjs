// gen_figs.mjs — build inline SVG figures + tables and inject into the report HTML
import fs from 'node:fs';
const ROOT = 'D:/M/大数据实践/8. Linear-models';
const RD = JSON.parse(fs.readFileSync(ROOT + '/.tmp/linear-models/results/report_data.json', 'utf8'));
const RA = JSON.parse(fs.readFileSync(ROOT + '/.tmp/linear-models/results/report_anchors.json', 'utf8'));
const HTML_PATH = ROOT + '/report/linear-models-crossover.html';
const LDA = '#2b6ca3', LOG = '#c2573b', BAY = '#666', GRID = '#d5d5d5', TXT = '#333';

const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
const expit = z => 1 / (1 + Math.exp(-z));
const fmt = (v, n = 4) => v == null ? '—' : (+v).toFixed(n);

function svgWrap(w, h, body, title) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" font-family="Segoe UI,Microsoft YaHei,sans-serif"><title>${esc(title)}</title>${body}</svg>`;
}
function line(x1, y1, x2, y2, s, w, dash) {
  return `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="${s}" stroke-width="${w}"${dash ? ` stroke-dasharray="${dash}"` : ''}/>`;
}
function txt(x, y, t, s, c, anchor, weight) {
  return `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" font-size="${s || 12}" fill="${c || TXT}"${anchor ? ` text-anchor="${anchor}"` : ''}${weight ? ` font-weight="${weight}"` : ''}>${esc(t)}</text>`;
}

/* ---------- F1 boundary landscape ---------- */
function f1() {
  const P = RA.plot; const W = 640, H = 420, m = { l: 52, r: 16, t: 24, b: 40 };
  const xlo = -2.2, xhi = 4.4, ylo = -3.2, yhi = 3.2;
  const sx = v => m.l + (v - xlo) / (xhi - xlo) * (W - m.l - m.r);
  const sy = v => H - m.b - (v - ylo) / (yhi - ylo) * (H - m.t - m.b);
  let g = '';
  // grid + axes
  for (let x = -2; x <= 4; x++) g += line(sx(x), m.t, sx(x), H - m.b, GRID, 1);
  for (let y = -3; y <= 3; y++) { g += line(m.l, sy(y), W - m.r, sy(y), GRID, 1); g += txt(m.l - 6, sy(y) + 4, y, 11, '#777', 'end'); }
  for (let x = -2; x <= 4; x++) g += txt(sx(x), H - m.b + 16, x, 11, '#777', 'middle');
  g += txt(W / 2, H - 6, 'x₁（标准化后，类间分离方向）', 12, TXT, 'middle');
  g += txt(14, H / 2, 'x₂', 12, TXT, 'middle');
  // scatter
  for (const [p, lab] of P.pts) {
    g += `<circle cx="${sx(p[0]).toFixed(1)}" cy="${sy(p[1]).toFixed(1)}" r="2.6" fill="${lab ? '#e08a3c' : '#8a99a8'}" fill-opacity=".75"/>`;
  }
  // vertical-ish decision lines x = (-b0 - b2*y)/b1
  const seg = (beta, b0, col, dash) => {
    const xAt = y => (-b0 - beta[1] * y) / beta[0];
    const y1 = ylo, y2 = yhi, x1 = xAt(y1), x2 = xAt(y2);
    return line(sx(Math.max(xlo, Math.min(xhi, x1))), sy(y1), sx(Math.max(xlo, Math.min(xhi, x2))), sy(y2), col, 2.2, dash);
  };
  g += seg([RA.e3a ? 1.46575 : 1.46575, 0], -0.5 * 1.46575 * 1.46575 + Math.log(0.44 / 0.56), BAY, '5,4'); // Bayes truth
  g += seg(P.lda[0], P.lda[1], LDA, null);
  g += seg(P.logit[0], P.logit[1], LOG, null);
  // legend
  g += `<g transform="translate(${W - 236},${m.t + 6})"><rect x="-8" y="-12" width="232" height="72" fill="#fff" fill-opacity=".9" stroke="${GRID}"/>` +
    line(0, 0, 26, 0, LDA, 2.2) + txt(32, 4, `LDA：x₁ 交点 ${(-P.lda[1] / P.lda[0][0]).toFixed(3)}`, 11.5, LDA) +
    line(0, 18, 26, 18, LOG, 2.2) + txt(32, 22, `Logistic：x₁ 交点 ${(-P.logit[1] / P.logit[0][0]).toFixed(3)}`, 11.5, LOG) +
    line(0, 36, 26, 36, BAY, 2, '5,4') + txt(32, 40, '贝叶斯真边界 x₁=0.898', 11.5, BAY) +
    line(0, 54, 26, 54, BAY, 0) + txt(32, 58, '● 橙=阳性 π₁=0.44　● 灰=阴性', 11, '#555') + `</g>`;
  return svgWrap(W, H, g, '边界地形');
}

/* ---------- F2 win-rate curves ---------- */
function f2() {
  const axes = [
    { k: 'e1_d5', title: 'n 轴（d=5, λ=0, γ=1）', logx: false, xfmt: v => 'n=' + Math.round(10 ** v), xrange: [1.5, 3.4], note: '交叉 n≈2641 → 超出数据范围（外推，不采信）' },
    { k: 'e2_d', title: 'd 轴（n=300, λ=γ条件干净）', xfmt: v => 'd=' + Math.round(v), xrange: [1, 52], note: 'soft 交叉 d≈22，全段 |ΔAUC|≤0.0012' },
    { k: 'e3a_lam', title: 'λ 轴（协方差分歧）', xfmt: v => 'λ=' + (+v).toFixed(1), xrange: [-0.05, 1.05], note: '拟合交叉 λ≈0.50 —— 平局区噪声，判无' },
    { k: 'e3b_gamma', title: 'γ 轴（边际偏态）', xfmt: v => 'γ=' + (+v).toFixed(1), xrange: [0.95, 2.05], note: '交叉 γ≈1.08 —— 真实且陡峭：γ≥1.3 起 Logistic 稳定占优' },
  ];
  const PW = 320, PH = 215, W = 716, H = 500;
  let g = '';
  axes.forEach((ax, i) => {
    const A = RD.axis[ax.k]; if (!A) return;
    const ox = 40 + (i % 2) * (PW + 16), oy = 30 + Math.floor(i / 2) * (PH + 25);
    const ylo = 0.2, yhi = 0.62;
    const xlo = ax.xrange[0], xhi = ax.xrange[1];
    const sx = v => ox + 46 + (v - xlo) / (xhi - xlo) * (PW - 62);
    const sy = v => oy + PH - 34 - (v - ylo) / (yhi - ylo) * (PH - 52);
    let p = `<g><rect x="${ox}" y="${oy}" width="${PW}" height="${PH}" fill="#fff" stroke="${GRID}"/>`;
    p += txt(ox + PW / 2, oy + 15, ax.title, 12, TXT, 'middle', '600');
    p += line(ox + 46, sy(0.5), ox + PW - 16, sy(0.5), '#999', 1, '4,3');
    p += txt(ox + 42, sy(0.5) + 4, '0.5', 10, '#999', 'end');
    // fitted curve
    let path = '';
    for (let t = 0; t <= 60; t++) {
      const x = xlo + (xhi - xlo) * t / 60; const wp = expit(A.a + A.b * x);
      path += (t ? 'L' : 'M') + sx(x).toFixed(1) + ' ' + sy(Math.max(ylo, Math.min(yhi, wp))).toFixed(1);
    }
    p += `<path d="${path}" fill="none" stroke="#4b7ba8" stroke-width="1.6" stroke-opacity=".85"/>`;
    // points
    A.xs.forEach((x, k) => { const w = A.win_rates[k]; p += `<circle cx="${sx(x).toFixed(1)}" cy="${sy(w).toFixed(1)}" r="3.4" fill="${w > 0.5 ? LDA : LOG}"/>`; });
    // x ticks (sorted few)
    const pts = A.xs.slice().sort((u, v) => u - v);
    (pts.length <= 5 ? pts : [pts[0], pts[pts.length - 1]]).forEach(x => { p += txt(sx(x), oy + PH - 18, ax.xfmt(x), 9.5, '#777', 'middle'); });
    if (ax.k === 'e1_d5') [1.6021, 2, 2.301, 2.699, 3, 3.301].forEach(x => { p += txt(sx(x), oy + PH - 18, ax.xfmt(x), 8.5, '#777', 'middle'); });
    if (ax.k === 'e2_d') [2, 10, 30, 50].forEach(x => { p += txt(sx(x), oy + PH - 18, ax.xfmt(x), 9, '#777', 'middle'); });
    if (ax.k === 'e3a_lam') [0, 0.4, 0.8, 1].forEach(x => { p += txt(sx(x), oy + PH - 18, ax.xfmt(x), 9, '#777', 'middle'); });
    if (ax.k === 'e3b_gamma') [1, 1.3, 1.6, 2].forEach(x => { p += txt(sx(x), oy + PH - 18, ax.xfmt(x), 9, '#777', 'middle'); });
    // crossover marker
    if (A.xover > xlo && A.xover < xhi && ax.k !== 'e1_d5') p += line(sx(A.xover), oy + 24, sx(A.xover), oy + PH - 30, '#2a7f4f', 1.4, '3,3');
    p += txt(ox + 8, oy + PH - 4, ax.note, 9.6, '#555');
    p += '</g>'; g += p;
  });
  g += `<g transform="translate(46,${H - 6})">${line(0, -3, 12, -3, LDA, 2.4)}${txt(16, 0, 'LDA 胜率 >0.5', 11, LDA)}${line(110, -3, 122, -3, LOG, 2.4)}${txt(126, 0, '<0.5（Logistic 占优）', 11, LOG)}</g>`;
  return svgWrap(W, H, g, '胜率交叉曲线');
}

/* ---------- F4 cost bars ---------- */
function f4() {
  const groups = [
    { n: '心脏 270', v: [29.0, 13.0, 14.2, 8.7] },
    { n: '乳腺 569', v: [43.5, 25.0, 4.7, 3.9] },
    { n: 'Pima keep0', v: [80.6, 34.7, 66.2, 34.0] },
    { n: 'Pima drop0', v: [38.2, 16.8, 31.7, 16.4] },
  ];
  const W = 660, H = 330, m = { l: 56, r: 12, t: 34, b: 46 };
  const maxv = 85, sy = v => H - m.b - v / maxv * (H - m.t - m.b);
  let g = '';
  for (let v = 0; v <= 80; v += 20) { g += line(m.l, sy(v), W - m.r, sy(v), GRID, 1) + txt(m.l - 6, sy(v) + 4, v, 10.5, '#777', 'end'); }
  g += txt(16, 22, '代价 C=5·FN+FP（每次重复测试集均值）', 12, TXT);
  const bw = 30, gap = 6, gw = 4 * bw + 3 * gap;
  groups.forEach((gr, gi) => {
    const ox = m.l + 26 + gi * ((W - m.l - m.r - 40) / 4);
    gr.v.forEach((v, bi) => {
      const isL = bi < 2, at05 = bi % 2 === 0;
      const col = isL ? LDA : LOG;
      const x = ox + bi * (bw + gap);
      g += `<rect x="${x}" y="${sy(v)}" width="${bw}" height="${H - m.b - sy(v)}" fill="${col}" fill-opacity="${at05 ? 1 : 0.45}" rx="2"/>`;
      g += txt(x + bw / 2, sy(v) - 5, v.toFixed(1), 10.5, col, 'middle', '600');
    });
    g += txt(ox + gw / 2, H - m.b + 18, gr.n, 12, TXT, 'middle', '600');
    g += txt(ox + gw / 2, H - m.b + 33, '实=τ=0.5　淡=τ*(内层选优)', 9.5, '#777', 'middle');
  });
  g += `<g transform="translate(${W - 250},14)">${line(0, -3, 12, -3, LDA, 3)}${txt(16, 0, 'LDA', 11.5, LDA)}${line(52, -3, 64, -3, LOG, 3)}${txt(68, 0, 'Logistic', 11.5, LOG)}</g>`;
  return svgWrap(W, H, g, '代价对比');
}

/* ---------- F5 λ/γ AUC trajectories ---------- */
function f5() {
  const lamOrder = ['0', '0.1', '0.2', '0.4', '0.6', '0.8', '1'];
  const E = RA.e3a, G = RD.e3b.slice().sort((a, b) => a.g - b.g);
  const W = 660, H = 300;
  const panel = (ox, ow, title, xlo, xhi, ylo, yhi, series, extra, xt) => {
    let p = `<rect x="${ox}" y="20" width="${ow}" height="${H - 50}" fill="#fff" stroke="${GRID}"/>` + txt(ox + ow / 2, 12, title, 12.5, TXT, 'middle', '600');
    const sx = v => ox + 48 + (v - xlo) / (xhi - xlo) * (ow - 66);
    const sy = v => H - 34 - (v - ylo) / (yhi - ylo) * (H - 90);
    for (let i = 0; i <= 4; i++) { const v = ylo + (yhi - ylo) * i / 4; p += line(ox + 48, sy(v), ox + ow - 14, sy(v), GRID, .8) + txt(ox + 44, sy(v) + 3.5, v.toFixed(2), 9.5, '#777', 'end'); }
    xt.forEach(x => { p += txt(sx(x), H - 20, String(x), 10, '#777', 'middle'); });
    series.forEach(s => {
      let path = ''; s.pts.forEach(([x, y], i) => { path += (i ? 'L' : 'M') + sx(x).toFixed(1) + ' ' + sy(y).toFixed(1); });
      p += `<path d="${path}" fill="none" stroke="${s.c}" stroke-width="2"${s.dash ? ` stroke-dasharray="${s.dash}"` : ''}/>`;
      s.pts.forEach(([x, y]) => { p += `<circle cx="${sx(x).toFixed(1)}" cy="${sy(y).toFixed(1)}" r="3" fill="${s.c}"/>`; });
    });
    if (extra) p += extra(sx, sy);
    return p;
  };
  let g = panel(0, 330, 'λ 轴：共同时钟下的天花板坍塌（AUC）', 0, 1, 0.68, 0.93, [
    { c: BAY, dash: '5,4', pts: lamOrder.map((k, i) => [+k, E[k].bayes]) },
    { c: LDA, pts: lamOrder.map(k => [+k, E[k].lda]) },
    { c: LOG, pts: lamOrder.map(k => [+k, E[k].logit]) },
  ], (sx, sy) => `<path d="M${sx(1)} ${sy(E['1'].qda)} l-5 0 l5 -8.6 l5 8.6 z" fill="#b8860b"/>` + txt(sx(1) - 8, sy(E['1'].qda) + 14, 'QDA 0.877', 10.5, '#b8860b', 'end'), [0, 0.4, 0.8, 1]);
  // λ legend inside left panel
  g += `<g transform="translate(64,${H - 78})" font-size="10.5">${txt(0, 0, '— 灰虚线：贝叶斯上界（升）', 10.5, BAY)}${txt(0, 14, '● 蓝：LDA', 10.5, LDA)}${txt(70, 14, '● 红：Logistic', 10.5, LOG)}</g>`;
  const gm = { 1: 0.8503, 1.3: 0.8503, 1.6: 0.8503, 2: 0.8503 };
  g += panel(330 + 20, 310, 'γ 轴：真正的交叉（AUC）', 0.95, 2.05, 0.81, 0.865, [
    { c: BAY, dash: '5,4', pts: G.map(e => [e.g, gm[e.g] || e.bayes]) },
    { c: LDA, pts: G.map(e => [e.g, e.lda]) },
    { c: LOG, pts: G.map(e => [e.g, e.logit]) },
  ], null, [1, 1.3, 1.6, 2]);
  g += txt(360 + 20, H - 44, 'γ=2：LDA −0.029 / Log −0.020 于上界；ΔAUC=−0.0086（p<0.001）', 10, '#555');
  return svgWrap(W, H, g, '违背轴轨迹');
}

/* ---------- F6 verdict heatmap ---------- */
function f6() {
  const rows = RD.regime.slice().sort((a, b) => a.t.localeCompare(b.t));
  const RW = 22, W = 660, H = rows.length * RW + 74;
  const col = r => r.v === 'LDA' ? LDA : r.v === 'Logit' ? LOG : r.v === 'tie-systematic' ? (r.d > 0 ? '#9dbdd9' : '#e3b7a4') : '#e8e8e8';
  let g = txt(10, 16, 'stage / 点', 11.5, TXT, 'start', '600');
  g += txt(560, 16, '胜率', 11.5, TXT, 'middle', '600') + txt(635, 16, 'ΔAUC', 11.5, TXT, 'middle', '600');
  rows.forEach((r, i) => {
    const y = 28 + i * RW;
    g += `<rect x="10" y="${y}" width="${W - 20}" height="${RW - 2}" fill="${col(r)}" fill-opacity="${r.v === 'undecided' ? .5 : 1}" rx="2"/>`;
    g += txt(18, y + 14, r.t.replace(/_lam0_g1/, '').replace(/_lam/, '·λ').replace(/_g/, '·γ').replace(/_d/, '·d').replace(/_n/, '·n'), 10.6, r.v === 'undecided' ? '#555' : '#fff');
    g += txt(560, y + 14, r.wr.toFixed(3), 10.6, r.v === 'undecided' ? '#444' : '#fff', 'middle');
    g += txt(640, y + 14, (r.d > 0 ? '+' : '') + r.d.toFixed(4), 10.6, r.v === 'undecided' ? '#444' : '#fff', 'end');
  });
  g += `<g transform="translate(18,${H - 16})" font-size="10.5">${txt(0, 0, '■', 11, LDA)} LDA 胜　${txt(56, 0, '■', 11, LOG)} Logistic 胜　${txt(150, 0, '■', 11, '#9dbdd9')} 系统性平局(LDA微优)　${txt(310, 0, '■', 11, '#e3b7a4')} 系统性平局(Log微优)　${txt(480, 0, '■', 11, '#bbb')} 未判定</g>`;
  return svgWrap(W, H, g, '判定热力图');
}

/* ---------- tables ---------- */
function tagInfo(t) {
  let mm; const o = { stage: t.split('_')[0] };
  if (t === 'e6_heart') o.dset = '心脏'; if (t === 'e6_bcw') o.dset = '乳腺';
  if (t.startsWith('e6_pima')) o.dset = 'Pima ' + t.slice(7);
  if ((mm = t.match(/_n(\d+)_d(\d+)/))) { o.n = mm[1]; o.d = mm[2]; }
  else if ((mm = t.match(/_n(\d+)/))) o.n = mm[1];
  if ((mm = t.match(/_d(\d+)/))) o.d = o.d || mm[1];
  if ((mm = t.match(/_d(\d+)_lam([\d.]+)/))) { o.d = mm[1]; o.lam = mm[2]; }
  else if ((mm = t.match(/_lam([\d.]+)/))) o.lam = mm[1];
  if ((mm = t.match(/_g([\d.]+)/))) o.gam = mm[1];
  if (/qda/.test(t)) o.tag = 'QDA探针';
  return o;
}
function vchip(v) {
  const cls = v === 'LDA' ? 'verdict-LDA' : v === 'Logit' ? 'verdict-Logit' : v === 'tie-systematic' ? 'verdict-tie' : 'verdict-undecided';
  const lab = v === 'tie-systematic' ? '系统平局' : v === 'undecided' ? '未判定' : v;
  return `<span class="${cls}">${lab}</span>`;
}
function pfmt(p) { return p == null ? '—' : p < 0.0001 ? p.toExponential(1) : p.toFixed(4); }
function regimeTable() {
  const picks = ['e3b_n300_d5_lam0_g1', 'e3b_n300_d5_lam0_g1.3', 'e3b_n300_d5_lam0_g1.6', 'e3b_n300_d5_lam0_g2',
    'e3a_n300_d5_lam0_g1', 'e3a_n300_d5_lam0.8_g1', 'e5_n40_d5_lam0_g1_f0-0.25-0.5-1_st', 'e6_heart', 'e6_bcw', 'e6_pima_keep0'];
  const idx = {}; RD.regime.forEach(r => idx[r.t] = r);
  let tr = '';
  for (const t of picks) { const r = idx[t]; if (!r) continue; const o = tagInfo(t);
    tr += `<tr><td class="l">${t === 'e6_heart' ? '心脏锚点' : t === 'e6_bcw' ? '乳腺锚点' : t === 'e6_pima_keep0' ? 'Pima keep0' : t === 'e5_n40_d5_lam0_g1_f0-0.25-0.5-1_st' ? 'n40×收缩因子网格' : (o.n && o.d ? `n=${o.n}, d=${o.d}` : '') + (o.lam != null ? `, λ=${o.lam}` : '') + (o.gam ? `, γ=${o.gam}` : '')}</td>` +
      `<td>${r.d > 0 ? '+' : ''}${r.d.toFixed(4)}</td><td>${pfmt(r.ph)}</td><td>${r.wr.toFixed(3)}</td><td>${vchip(r.v)}</td></tr>`;
  }
  return `<table class="data"><caption>表 1：代表性比较点（ΔAUC=LDA−Logistic；完整 36 行见附录 A）</caption>` +
    `<tr><th>条件</th><th>Δ AUC</th><th>p (Holm)</th><th>LDA 胜率</th><th>判定</th></tr>${tr}</table>`;
}
function fullTable() {
  const rows = RD.regime.slice().sort((a, b) => a.t.localeCompare(b.t));
  let tr = '';
  for (const r of rows) { const o = tagInfo(r.t);
    tr += `<tr><td class="l">${r.t.replace('point_', '')}</td><td>${o.n || '—'}</td><td>${o.d || '—'}</td><td>${o.lam ?? '—'}</td><td>${o.gam || '1'}</td>` +
      `<td>${r.d > 0 ? '+' : ''}${r.d.toFixed(4)}</td><td>${pfmt(r.ph)}</td><td>${r.wr.toFixed(3)}</td><td>${vchip(r.v)}</td></tr>`;
  }
  return `<table class="data"><tr><th>点</th><th>n</th><th>d</th><th>λ</th><th>γ</th><th>ΔAUC</th><th>p(Holm)</th><th>胜率</th><th>判定</th></tr>${tr}</table>`;
}

export async function run() {
  let html = fs.readFileSync(HTML_PATH, 'utf8');
  const subs = { '<!--FIG:f1-->': f1(), '<!--FIG:f2-->': f2(), '<!--FIG:f4-->': f4(), '<!--FIG:f5-->': f5(), '<!--FIG:f6-->': f6(), '<!--TABLE:regimeTable-->': regimeTable(), '<!--TABLE:fullTable-->': fullTable() };
  for (const [k, v] of Object.entries(subs)) {
    if (!html.includes(k)) throw new Error('placeholder missing: ' + k);
    html = html.replace(k, v);
  }
  fs.writeFileSync(HTML_PATH, html);
  const left = (html.match(/<!--(FIG|TABLE):/g) || []).length;
  console.log('@@DSH_RESULT@@' + JSON.stringify({ size_kb: Math.round(html.length / 1024 * 10) / 10, placeholders_left: left }));
}
