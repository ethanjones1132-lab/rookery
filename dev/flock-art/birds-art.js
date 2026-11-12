// The Flock: pixel crows, v3. Original 48×44 sprites drawn natively in code (style reference:
// chunky indigo-black pixel crows; no third-party pixels are copied or shipped).
// Every color is a Hermes theme token, every motion moves in whole sprite pixels.
//
// House style of desktop/plugin.js (createElement as h, scoped CSS string), so it
// can be lifted into the plugin as-is.
//
//   <Bird id="quill" state="idle|singing|muted|dim" anim="land|leave|ruffle|null" bpm={90} size={96} />
//   --beak (0..1) on the bird's root opens the beak from real note events: ≥0.3 caws,
//   ≥0.7 is a big caw (the head tips back a pixel).
import { createElement as h, useEffect, useRef, useState } from 'react'

function resolveColor(el, cssValue) { const probe=document.createElement('span'); probe.style.color=cssValue; probe.style.display='none'; el.appendChild(probe); const color=getComputedStyle(probe).color; probe.remove(); return color }

// ── the cast ─────────────────────────────────────────────────────────────
// eyes: plain · wide · sleepy · cool · kind · regal  (brows and lids drawn in pixels)
// fx: notes · zzz · sparkle (pixel particles with meaning)
export const CAST = [
  { id: 'bramble', name: 'Bramble', species: 'rook', role: 'bass', costume: 'cap', accent: 'var(--ui-orange)', eyes: 'kind', fx: 'notes', persona: 'Steady, unbothered. Nods on every beat.', gesture: 'nod' },
  { id: 'cinder', name: 'Cinder', species: 'crow', role: 'bass', costume: 'chain', accent: 'var(--ui-yellow)', eyes: 'cool', fx: 'sparkle', persona: 'Swagger. Leans back between notes.', gesture: 'lean' },
  { id: 'quill', name: 'Quill', species: 'rook', role: 'keys', costume: 'beret', accent: 'var(--ui-cyan)', eyes: 'plain', fx: 'notes', persona: 'The jazz head. Wing-taps the chords.', gesture: 'tap' },
  { id: 'sable', name: 'Sable', species: 'raven', role: 'keys', costume: 'tophat', accent: 'var(--ui-purple)', eyes: 'regal', fx: 'notes', persona: 'Formal and theatrical. Tips the hat on bar one.', gesture: 'sway' },
  { id: 'jinx', name: 'Jinx', species: 'jackdaw', role: 'lead', costume: 'crest', accent: 'var(--ui-red)', eyes: 'wide', fx: 'notes', persona: 'Show-off. Hops on the accents.', gesture: 'hop' },
  { id: 'glint', name: 'Glint', species: 'magpie', role: 'lead', costume: 'monocle', accent: 'var(--ui-yellow)', eyes: 'plain', fx: 'sparkle', persona: "Can't resist anything shiny.", gesture: 'tilt' },
  { id: 'hush', name: 'Hush', species: 'raven', role: 'pad', costume: 'nightcap', accent: 'var(--ui-blue)', eyes: 'sleepy', fx: 'zzz', persona: 'Always half asleep. Breathes like a slow pad.', gesture: 'doze' },
  { id: 'moss', name: 'Moss', species: 'rook', role: 'pad', costume: 'knit', accent: 'var(--ui-green)', eyes: 'kind', fx: 'notes', persona: 'Cozy. Settles its feathers.', gesture: 'settle' },
  { id: 'tick', name: 'Tick', species: 'chough', role: 'arp', costume: 'goggles', accent: 'var(--ui-orange)', eyes: 'wide', fx: 'notes', persona: 'Nervous energy. Twitches every sixteenth.', gesture: 'twitch' },
  { id: 'pip', name: 'Pip', species: 'jackdaw', role: 'arp', costume: 'propeller', accent: 'var(--ui-cyan)', eyes: 'wide', fx: 'notes', persona: 'Playful. The propeller spins when it sings.', gesture: 'bounce' },
  { id: 'echo', name: 'Echo', species: 'crow', role: 'call', costume: 'silk', accent: 'var(--ui-purple)', eyes: 'plain', fx: 'notes', persona: 'The singer. Throws its head back on every phrase.', gesture: 'belt' },
  { id: 'wrennot', name: 'Wren-Not', species: 'rook', role: 'call', costume: 'flower', accent: 'var(--ui-red)', eyes: 'kind', fx: 'notes', persona: "Insists it isn't a wren.", gesture: 'answer' },
  { id: 'corvus', name: 'Corvus', species: 'crow', role: 'crown', costume: 'crown', accent: 'var(--ui-accent)', eyes: 'regal', fx: 'sparkle', persona: 'The king. Arrives when the whole flock has sung.', gesture: 'regal', secret: true }
]
export const CAST_BY_ID = Object.fromEntries(CAST.map(b => [b.id, b]))

// ── base sprite: a perched crow facing right, drawn natively at 48 × 44 ─────────
// Hand-shaded final pixel codes, four tones per material:
//   body o outline · M shadow · d base · r light      wing p shadow · m base · h / H sheen (blue / purple)
//   bill o outline · M gape · Y base · y light         eye o pupil · e catch-light      legs Y base · l light
// Species, eyes, the caw and costumes are patches painted over it in compose().
const W = 48, H = 44
const MASK = [
  '................................................', // 0
  '................................................', // 1
  '................................................', // 2
  '................................................', // 3
  '................................................', // 4
  '................................................', // 5
  '................................................', // 6
  '................................................', // 7
  '................................................', // 8
  '.......................ooooooooooo..............', // 9
  '......................orrrrrrrrrrroooo..........', // 10
  '.....................orrrdddddddddddyyyooo......', // 11
  '.....................orddddddeoddddMYyyyyyoo....', // 12
  '.....................orddddddoodddMYYYYYYyyyo...', // 13
  '.....................ordddddddddddYYYYYYYYYYyo..', // 14
  '.....................ordddddddddddMYYYYYYYYYYYo.', // 15
  '.....................ordddddddddddMMMMMMMMMMYYo.', // 16
  '.....................orddddddddddMMYYYYYYYYooo..', // 17
  '....................orddddddddddMMMoooooooo.....', // 18
  '....................orddddddddMMMMdo............', // 19
  '...................ormmhhhmMdddddrddro..........', // 20
  '...................orhhhhhhHHMddddMdo...........', // 21
  '..................orhhhhhHHHHmMdrrddrro.........', // 22
  '..................orhhhHHHHHmmmMddMddo..........', // 23
  '.................ommHHHHHmmmmmmMdrddrrdo........', // 24
  '.................omHHHmmmmmmmpppMdMdddo.........', // 25
  '................ommmmmmmmmpppmmmMddrddo.........', // 26
  '................ommmmmmpppmmmhpmMrddddo.........', // 27
  '...............ommmmpppmmmmmhpmmMddddMo.........', // 28
  '...............ompppmmmmmmmmpmmodddddMo.........', // 29
  '..............ompmmmmmmmmmmpmmmodddMMo..........', // 30
  '..............ommmmmmmmmmmpmmmoddddMMo..........', // 31
  '.............opppmmmmmmmmpmmmodddMMMo...........', // 32
  '.............oppmppmmmmmpmmmoddMMMMo............', // 33
  '............oppmpppmpmmpmmoddMMMMMo.............', // 34
  '............opmpppmppppmoddMMMMMMo..............', // 35
  '...........opmpppmpppmoMMoMMMMoo................', // 36
  '..........opmpppmpmooMooYo.olYo.................', // 37
  '.........opmppmopopMo..oYo.olYo.................', // 38
  '........opmmopopMMo....oYo.olYo.................', // 39
  '.......omopopMMMo......oYo.olYo.................', // 40
  '......ommppMMo.......oYYYo.olllllo..............', // 41
  '.....ompMMo.........oYooYolYo.oYYo..............', // 42
  '....oooo.............o....o......o..............'  // 43
]
const HEAD = { y0: 8, y1: 19, x0: 20 }
const SHOULDER_Y = 20

// Species patches: [x, y, rows] painted over the base ('.' keeps a pixel, '_' erases it).
// iris: the eye color (jackdaw's pale eye) · legs: the leg color (chough's red legs).
const SPECIES = {
  crow: {},
  rook: { // bare pale face, slimmer bill, shaggy "trousers"
    paint: [
      [32, 11, ['..gw', 'gwwg', 'gwg.', 'gg..', 'ggg.', '.gg.', 'ggg.', 'gggg']],
      [32, 19, ['gg']],
      [43, 13, ['yo_', 'Yyo', 'YYo', 'Yo_', 'o__']],
      [22, 35, ['.oMddMdMMo', 'oMdMdMdMdMo', 'oMoMoMoMMo', '.o.o.o.oo']]
    ]
  },
  raven: { // bigger hooked bill, heavy shaggy hackles
    paint: [
      [34, 10, ['oooooo']],
      [36, 11, ['yyyyyoo']],
      [35, 12, ['MYyyyyyyoo']],
      [34, 13, ['MYYYYYYYyyyo']],
      [34, 14, ['YYYYYYYYYYYyo']],
      [34, 15, ['MYYYYYYYYYYYYo']],
      [34, 16, ['MMMMMMMMMMYYYo']],
      [33, 17, ['MMYYYYYYYYYoYo']],
      [35, 18, ['ooooooooo_o']],
      [33, 19, ['drdrdo']],
      [33, 20, ['dMddrro']],
      [33, 21, ['rdMdo_']],
      [32, 22, ['rdrddrro']],
      [33, 23, ['MdMdo_']],
      [33, 24, ['rdMdrro']],
      [34, 25, ['MdMdo']],
      [35, 26, ['rddo']]
    ]
  },
  jackdaw: { // grey nape, pale eye, short bill
    iris: 'w',
    paint: [
      [22, 12, ['gg']],
      [22, 13, ['gggg']],
      [22, 14, ['ggggg']],
      [21, 15, ['oggggggg']],
      [21, 16, ['ogggggg']],
      [21, 17, ['ogggggg']],
      [20, 18, ['oggggg']],
      [20, 19, ['ogggg']],
      [19, 20, ['og']],
      [34, 10, ['ooo____']],
      [36, 11, ['yyoo____']],
      [35, 12, ['MYyyoo____']],
      [34, 13, ['MYYYYyo_____']],
      [34, 14, ['YYYYYYyo____']],
      [34, 15, ['MYYYYYYo_____']],
      [34, 16, ['MMMMMMYo_____']],
      [33, 17, ['MMYYYYYo______']],
      [35, 18, ['oooooo____']]
    ]
  },
  magpie: { // white belly and scapular bar, long sheened tail
    paint: [
      [31, 26, ['owwwwww']],
      [29, 27, ['oowwwwwww']],
      [29, 28, ['owwwwwwwg']],
      [28, 29, ['owwwwwwwwg']],
      [28, 30, ['owwwwwwgg']],
      [27, 31, ['owwwwwwwgg']],
      [26, 32, ['owwwwwwggg']],
      [25, 33, ['owwwwwgggg']],
      [24, 34, ['owwwwgggg']],
      [24, 35, ['oggggggggo']],
      [20, 20, ['..ww']],
      [20, 21, ['.wwwww']],
      [19, 22, ['owwwww']],
      [18, 23, ['owwwww']],
      [17, 24, ['owww']],
      [0, 39, ['......oo', '....oohm', '..oohhm', 'oohhmm', 'ommmpp']],
      [0, 43, ['oooooo']]
    ]
  },
  chough: { // red, slender, down-curved bill; red legs
    legs: 'R',
    paint: [
      [34, 10, ['o___']],
      [34, 11, ['dooo_______']],
      [34, 12, ['MRRRoo______']],
      [34, 13, ['MeRRRRoo____']],
      [34, 14, ['MRRRRRRRo___']],
      [34, 15, ['MRRRRRRRRo__']],
      [34, 16, ['MMMMMMMRRRo_']],
      [33, 17, ['MMRRRRRRoRRo']],
      [35, 18, ['oooooo_oRo']],
      [43, 19, ['o']]
    ]
  }
}

// Eyes: E iris (species color) · e catch-light · any other code is drawn as is (lids, brows).
const EYES = {
  plain: [[29, 12, 'e'], [30, 12, 'E'], [29, 13, 'E'], [30, 13, 'E']],
  wide: [[29, 11, 'e'], [30, 11, 'E'], [29, 12, 'E'], [30, 12, 'E'], [29, 13, 'E'], [30, 13, 'E'], [28, 12, 'E'], [28, 11, 'o']],
  sleepy: [[28, 12, 'M'], [29, 12, 'M'], [30, 12, 'M'], [31, 12, 'M'], [29, 13, 'e'], [30, 13, 'E'], [31, 13, 'o']],
  cool: [[28, 11, 'o'], [29, 11, 'o'], [30, 11, 'o'], [31, 11, 'o'], [29, 12, 'M'], [30, 12, 'M'], [29, 13, 'e'], [30, 13, 'E']],
  kind: [[29, 12, 'e'], [30, 12, 'E'], [28, 13, 'o'], [29, 13, 'r'], [30, 13, 'r'], [31, 13, 'o']],
  regal: [[28, 11, 'o'], [29, 10, 'o'], [30, 10, 'o'], [29, 12, 'M'], [30, 12, 'E'], [29, 13, 'e'], [30, 13, 'E']]
}
const BLINK = [[29, 11, 'd'], [30, 11, 'd'], [28, 12, 'd'], [29, 12, 'M'], [30, 12, 'M'], [28, 13, 'o'], [29, 13, 'o'], [30, 13, 'o'], [31, 13, 'M']]

// Caw: below the gape the lower mandible drops (1px at the base, 2px further out), the bill
// tip lifts a pixel so the head reads tipped back, and the mouth shows dark with a tongue.
const CAW = { x0: 35, gape: 16, liftFrom: 40 }

// Wing raised (take-off and landing frame): repaints the folded wing as body and tail, and
// lifts the near wing with its primaries fanned. gridForFrame draws it one row up, hence y + 1.
const WING_UP = { x: 4, y: 1, rows: [
  '.........oo.................',
  '......oo.omo................',
  '...oo.omoompo...............',
  '.oomoompmpmpo...............',
  'ompmpmpmpppmo...............',
  'omppmppmpphho...............',
  '.ompmppmphhHo...............',
  'ompppmpmhhHHho..............',
  'omppppmmhHHhho..............',
  '.omppmmmhHhhhmo.............',
  '.omppmmmmHhhmmo.............',
  '..ompmmmmmhhmmmo............',
  '..omppmmmmmhmmmo............',
  '...ompmmmmmmmmmmo...........',
  '...oompmmmmpmmmmm...........',
  '....oompmmmmpmmmm...........',
  '.....oompmmmmpmmmmo.........',
  '......oomppmmmpmmmmo........',
  '........oomppmmmpmmmo.......',
  '..........ooppmmmpmmMo......',
  '............ooppp..mMod.....',
  '..............o.ppmMModdd...',
  '................oooodddddd..',
  '................ddddddddddd.',
  '..............rdddddddddddd.',
  '..............rddddddddddddd',
  '.............rdddddddddddddd',
  '.............rdddddddddddddd',
  '............rddddddddddddddd',
  '............rddddddddddddddd',
  '...........rdddddddddddddddd',
  '...........rMMMMMMMMMMMMMMM.',
  '..........rMMMMMMMMMMMMMMM..',
  '..........MMMMMMMMMMMMMMM...',
  '.........MMMMMMMMMMMMMM.....',
  '.........MM.MMMMMMMMM.......',
  '........MM.MMMM.MMM..M....M.',
  '.......MM.MMMMp.............',
  '......MM.MM.M.M.............',
  '.....MMp.M.M................',
  '....M...M...................',
  '...MM.M.....................'] }

// Costumes: x, y, rows (o outline · c accent · C accent detail · k light), optional alt frame (2-frame loop), on head or body.
const COSTUMES = {
  cap: { at: 'head', x: 21, y: 4, rows: [
    '....oooooooo',
    '...okkcccccoo',
    '..okcccccccCCo',
    '..occcccccccCCoooo',
    '.oCCCCCCCCCCCCcccco',
    '..oooooooooooooooo'] },
  beret: { at: 'head', x: 21, y: 3, rows: [
    '......oo',
    '.....oCo',
    '...oooooooooo',
    '.ookkccccccccoo',
    'okcccccccccccccco',
    'occccccccccccccco',
    '.oCCCCCCCCCCCCCo',
    '..ooooooooooooo',
    '......cccc',
    '.....c....c',
    'CCCCc.....kc',
    '....c......ccc',
    '.....c....c',
    '......cccc'] },
  tophat: { at: 'head', x: 21, y: 0, rows: [
    '...oooooooooo',
    '...okcccccccCo',
    '...okcccccccCo',
    '...okcccccccCo',
    '...okcccccccCo',
    '...oCCCCCCCCCo',
    '...okcccccccCo',
    'ooocccccccccccoooo',
    'okcccccccccccccccco',
    '.ooooooooooooooooo'] },
  crest: { at: 'head', x: 20, y: 1, rows: [
    'o.....o',
    'oco...oco...o',
    '.okco..okco.oco',
    '..okcco.okccokco',
    '...okccookcccco',
    '....okcccccccco',
    '.....occcccccCo',
    '......oCCCCCCo',
    '.......ooooooo'],
    alt: [
    '.o.....o',
    '.oco...oco...o',
    '..okco..okco.oco',
    '..okcco.okccokco',
    '...okccookcccco',
    '....okcccccccco',
    '.....occcccccCo',
    '......oCCCCCCo',
    '.......ooooooo'] },
  monocle: { at: 'head', x: 27, y: 10, rows: [
    '.cccc',
    'c...kc',
    'c....c',
    'c....c',
    'c....c',
    '.cccc',
    '..C',
    '...C',
    '...C',
    '....C',
    '....C',
    '.....k'] },
  nightcap: { at: 'head', x: 8, y: 2, rows: [
    '...............oooooo',
    '............oookkccccoo',
    '..........ookkcccccccccoo',
    '........ookccccccccccccccco',
    '......ookcccCccccccccccccco',
    '....oookccCo.oCCCCCCCCCCCCo',
    '..okkocccCo...ooooooooooooo',
    '.okkkkoCCo',
    '.okkkko.o',
    '..okko'],
    alt: [
    '...............oooooo',
    '............oookkccccoo',
    '..........ookkcccccccccoo',
    '........ookccccccccccccccco',
    '.......okccCcccccccccccccco',
    '.....ookcCCo.oCCCCCCCCCCCCo',
    '....okkoCCo...ooooooooooooo',
    '...okkkkoo',
    '...okkkko',
    '....okko'] },
  goggles: { at: 'head', x: 21, y: 5, rows: [
    '....oooo..oooo',
    '...okekcookekco',
    'oCCocckcoocckco',
    'oCCCoooo..oooo'] },
  propeller: { at: 'head', x: 21, y: 1, rows: [
    '..oooooo.oooooo',
    '..okkkkCoCcccco',
    '..oooooooooooo',
    '.......oCo',
    '....ooooCoooo',
    '..ookkcccccccoo',
    '.okccccccccccccoo',
    'oCCcCCcCCcCCcCCco',
    '.ooooooooooooooo'],
    alt: [
    '......oooooo',
    '......okCcco',
    '......oooooo',
    '.......oCo',
    '....ooooCoooo',
    '..ookkcccccccoo',
    '.okccccccccccccoo',
    'oCCcCCcCCcCCcCCco',
    '.ooooooooooooooo'] },
  crown: { at: 'head', x: 22, y: 3, rows: [
    '.o...o...o...o',
    'oko.oko.oko.oko',
    'okcoocccocccocCo',
    'okcccckccccccCCo',
    'occkccccccckccCo',
    'oCCCCCCCCCCCCCCo',
    '.oooooooooooooo'],
    alt: [
    '.o...o...o...o',
    'oko.oko.oko.oko',
    'okcoocccocccocCo',
    'okccccccccccccCo',
    'occCcccckccCccCo',
    'oCCCCCCCCCCCCCCo',
    '.oooooooooooooo'] },
  flower: { at: 'head', x: 19, y: 7, rows: [
    '..ooo',
    '.okcco',
    'okckkco',
    'occkcCo',
    '.occCo',
    '..oCoC',
    '.....C'] },
  chain: { at: 'body', x: 21, y: 18, rows: [
    'o..........o..',
    'Ck.......kCo',
    '.cC.....Cc',
    '..kCc.cCk',
    '....oko',
    '...okcco',
    '...occCo',
    '....oCo'],
    alt: [
    'o..........o..',
    'Cc.......cCo',
    '.kC.....Ck',
    '..cCk.kCc',
    '....oco',
    '...ocko',
    '...occCo',
    '....oCo'] },
  knit: { at: 'body', x: 19, y: 17, rows: [
    '.oooooooooooooooo',
    'okcCccCccCccCccCo',
    'occCccCccCccCccCco',
    '.oooooooooocCcCoo',
    '...........ocCco',
    '...........occCo',
    '...........ocCco',
    '...........occCo',
    '...........ocCco',
    '...........okkko',
    '...........k.k.k'] },
  silk: { at: 'body', x: 0, y: 14, rows: [
    '',
    '',
    '..........oooooo',
    '.o......ookkkkkkoo.ooooooooooooooooo',
    'ocooooookkcccccckkokkkkkkccccccccccc',
    'oCcccckkccCCCCCCcckccCCCCCCCCCCCCCkco',
    '.oCCCCccCCooooooCCcCCCooooooooooooccCo',
    '..ooooCCoo......ooCooo...........ocCo',
    '......oo..........o..............oCo',
    '.................................oco',
    '.................................oo',
    ''],
    alt: [
    '',
    '',
    '.......oooooo',
    '.....ookkkkkkoo....ooooooooooooooooo',
    '.oooockcccccckkooookkkkkkccccccccccc',
    'occccCcCCCCCCcckkkkccCCCCCCCCCCCCCkco',
    'oCCCCoCooooooCCccccCCCooooooooooooccCo',
    '.oooo.o......ooCCCCooo...........ocCo',
    '...............oooo..............oCo',
    '.................................oco',
    '.................................oo',
    ''] }
}

// Pixel particles (sprite pixels), placed near the beak / head.
const GLYPH = {
  note: ['..###', '..#.#', '..#..', '###..', '###..'],
  z: ['#####', '...#.', '..#..', '.#...', '#####'],
  spark: ['..#..', '..#..', '##.##', '..#..', '..#..']
}

// ── compose: base + species + caw + eyes → pixel grid ─────────────────────────
// Output codes: o outline · d body · r body light · M shadow · m wing · h / H sheen · p primaries
// y bill light · Y bill · e catch-light · w white · g grey · R red · l legs · c / C / k costume
function paint(g, x0, y0, rows) {
  rows.forEach((row, dy) => [...row].forEach((c, dx) => {
    const x = x0 + dx, y = y0 + dy
    if (c !== '.' && x >= 0 && x < W && y >= 0 && y < H) g[y][x] = c === '_' ? '.' : c
  }))
}

function openBill(g) {
  const { x0, gape, liftFrom } = CAW, src = g.map(r => r.slice())
  let lt = x0 - 1 // last column of the lower mandible
  while (lt + 1 < W && !'.o'.includes(src[gape + 1][lt + 1])) lt++
  for (let x = x0; x < W; x++) {
    const lower = x <= lt + 1, drop = lower ? (x < x0 + 2 ? 1 : 2) : 0, lift = x >= liftFrom ? 1 : 0
    const top = lower ? gape : gape + 4
    for (let y = 8; y <= (lower ? gape + 2 : top); y++) g[y][x] = '.'
    for (let y = 8; y <= top; y++) if (src[y][x] !== '.' && y - lift >= 0) g[y - lift][x] = src[y][x]
    if (!drop) continue
    for (const y of [gape + 1, gape + 2]) if (src[y][x] !== '.') g[y + drop][x] = src[y][x]
    if (x <= lt) for (let y = gape + 1 - lift; y < gape + 1 + drop; y++) g[y][x] = x < x0 + 3 && y === gape + drop ? 'R' : 'M'
  }
}

function compose(species, eyes, caw) {
  const g = MASK.map(r => r.padEnd(W, '.').slice(0, W).split(''))
  const sp = SPECIES[species] || SPECIES.crow
  ;(sp.paint || []).forEach(([x, y, rows]) => paint(g, x, y, rows))
  if (sp.legs) for (let y = 36; y < H; y++) for (let x = 18; x < 36; x++) if ('lY'.includes(g[y][x])) g[y][x] = sp.legs
  if (caw) openBill(g)
  ;(EYES[eyes] || EYES.plain).forEach(([x, y, c]) => { g[y][x] = c === 'E' ? sp.iris || 'o' : c === 'e' && sp.iris ? 'o' : c })
  return g
}

function rects(g, keep, key, cls) {
  const out = []
  for (let y = 0; y < g.length; y++) {
    let x = 0
    while (x < W) {
      const c = g[y][x]
      if (c === '.' || !keep(x, y)) { x++; continue }
      let x2 = x + 1
      while (x2 < W && g[y][x2] === c && keep(x2, y)) x2++
      out.push(h('rect', { key: `${key}${y}:${x}`, x, y, width: x2 - x, height: 1, className: cls || `p-${c}` }))
      x = x2
    }
  }
  return out
}

function stamp(rows, x0, y0, extra) {
  const g = Array.from({ length: H + 2 }, () => Array(W).fill('.'))
  rows.forEach((row, dy) => [...row].forEach((c, dx) => {
    const x = x0 + dx, y = y0 + dy + 1 // +1: costumes may sit one row above the canvas (tall hats)
    if (c !== '.' && x >= 0 && x < W && y >= 0 && y < H + 1) g[y][x] = c
  }))
  ;(extra || []).forEach(([x, y, c]) => { g[y + 1][x] = c })
  return g
}

function costume(kind, layer) {
  const cos = COSTUMES[kind]
  if (!cos || cos.at !== layer) return null
  const a = rects(stamp(cos.rows, cos.x, cos.y, cos.extra), () => true, 'ca')
  if (!cos.alt) return h('g', { className: 'c-costume', transform: 'translate(0 -1)' }, a)
  const b = rects(stamp(cos.alt, cos.x, cos.y, cos.extra), () => true, 'cb')
  return h('g', { className: 'c-costume', transform: 'translate(0 -1)' }, h('g', { className: 'c-a' }, a), h('g', { className: 'c-b' }, b))
}

function particles(kind) {
  if (!kind) return null
  const glyph = kind === 'zzz' ? GLYPH.z : kind === 'sparkle' ? GLYPH.spark : GLYPH.note
  const spots = kind === 'zzz' ? [[35, 3], [39, 0], [42, -1]] : kind === 'sparkle' ? [[38, 4], [15, 12], [41, 22]] : [[40, 3], [43, -1], [37, -1]]
  return h('g', { className: `fx fx-${kind}`, 'aria-hidden': true },
    spots.map(([x, y], i) => h('g', { key: i, className: `fx-p fx-p${i}` },
      rects(stamp(glyph, x, y), () => true, `fx${i}`))))
}

const inHead = (x, y) => y >= HEAD.y0 && y <= HEAD.y1 && x >= HEAD.x0

const BIRD_SPRITE_CACHE = new Map()
const SPRITE_W = 48, SPRITE_H = 44
const PX_CODES = ['o','d','r','M','m','p','h','H','y','Y','e','w','g','l','R','c','C','k','i','q']
const PX_FALLBACK = { o:'#11131c', d:'#25273c', r:'#777b9a', M:'#181a2b', m:'#343651', p:'#44465f', h:'#565a85', H:'#484a7b', y:'#c7b56c', Y:'#8f7746', e:'#11131c', w:'#f1efff', g:'#9ba4b8', l:'#c7b56c', R:'#c53953', c:'#bd78e8', C:'#9b67cb', k:'#7650a5', i:'#fff4d6', q:'#fff0bd' }
function gridForFrame(b, frame) {
  const g=compose(b.species,b.eyes,frame==='sing')
  const overlay=(rows,x,y,extra)=>{const layer=stamp(rows,x,y,extra);for(let py=0;py<H;py++)for(let px=0;px<W;px++)if(layer[py+1]?.[px]&&layer[py+1][px]!=='.')g[py][px]=layer[py+1][px]}
  const cos=COSTUMES[b.costume]; if(cos) overlay(cos.rows,cos.x,cos.y,cos.extra)
  if(frame==='wing') overlay(WING_UP.rows.map(r=>r.replace(/s/g,'h').replace(/w/g,'m')),WING_UP.x,WING_UP.y-1)
  if(frame==='blink')BLINK.forEach(([x,y,c])=>{g[y][x]=c})
  // The art is authored at the rig size (48×44), so this expansion is the identity.
  return Array.from({length:SPRITE_H},(_,y)=>Array.from({length:SPRITE_W},(_,x)=>g[Math.floor(y*H/SPRITE_H)][Math.floor(x*W/SPRITE_W)]))
}
function spriteUrl(id,b,frame,palette){
  const key=JSON.stringify([id,b.costume,b.species,b.eyes,frame,palette]);if(BIRD_SPRITE_CACHE.has(key))return BIRD_SPRITE_CACHE.get(key)
  const src=gridForFrame(b,frame),canvas=document.createElement('canvas');canvas.width=SPRITE_W;canvas.height=SPRITE_H
  const ctx=canvas.getContext('2d');ctx.imageSmoothingEnabled=false
  for(let y=0;y<SPRITE_H;y++)for(let x=0;x<SPRITE_W;x++){const c=src[y][x];if(c!=='.'){ctx.fillStyle=palette[c]||PX_FALLBACK[c]||'#fff';ctx.fillRect(x,y,1,1)}}
  const url=canvas.toDataURL();BIRD_SPRITE_CACHE.set(key,url);return url
}
export function BirdSVG({ id, title = true }) {
  const b=CAST_BY_ID[id];if(!b)return null
  const ref=useRef(null),[palette,setPalette]=useState(null)
  useEffect(()=>{const el=ref.current;if(!el)return
    const resolve=()=>{const next={};for(const code of PX_CODES){const value=getComputedStyle(el).getPropertyValue('--px-'+code).trim();next[code]=value?resolveColor(el,value):PX_FALLBACK[code]}setPalette(next)}
    resolve();const observer=new MutationObserver(resolve);observer.observe(document.documentElement,{attributes:true,attributeFilter:['class','style']});return()=>observer.disconnect()
  },[id])
  const blank='data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs='
  const urls=palette?['idle','blink','sing','wing'].map(frame=>spriteUrl(id,b,frame,palette)):[blank,blank,blank,blank]
  return h('div',{className:'fkb-svg b-root',role:'img','aria-label':title?b.name+', the '+b.species+', '+b.role:undefined,title:title?b.name+': '+b.persona:undefined},
    h('div',{ref,className:'fkb-frame-stack b-body b-head'},
      urls.map((src,i)=>h('img',{key:i,src,alt:'',draggable:false,className:['fkb-frame b-shut','fkb-frame b-lid','fkb-frame b-caw','fkb-frame b-wingup'][i]})),
      h('svg',{className:'fkb-particles',viewBox:`0 0 ${W} ${H-1}`,'aria-hidden':true},particles(b.fx))))
}

export function Bird({ id, state = 'idle', anim = null, bpm = 90, size = 96, seed = 0, onClick, label }) {
  const b = CAST_BY_ID[id]
  if (!b) return null
  const n = [...id].reduce((s, c) => (s * 31 + c.charCodeAt(0)) >>> 0, 7 + seed)
  const style = {
    '--beat': `${(60 / bpm).toFixed(4)}s`,
    '--blink': `${(3.2 + (n % 40) / 10).toFixed(2)}s`,
    '--breath': `${(2.6 + (n % 13) / 10).toFixed(2)}s`,
    '--phase': `-${((n % 97) / 31).toFixed(2)}s`,
    '--accent': b.accent,
    width: size, height: size * SPRITE_H / SPRITE_W
  }
  return h('button', {
    type: 'button', className: 'fkb', 'data-bird': id, 'data-gesture': b.gesture, 'data-state': state, 'data-anim': anim || undefined,
    style, onClick, 'aria-label': label || `${b.name}, ${b.role}${state === 'muted' ? ', muted' : state === 'singing' ? ', singing' : ''}`
  }, h(BirdSVG, { id }))
}

// ── palette + motion ────────────────────────────────────────────────────────
// Light themes: ink-dark crows. Dark themes: indigo-black bodies tinted by the accent,
// a rim light along the back, and a purple-blue iridescent sheen on the wing.
export const BIRD_CSS = `
.fkb{all:unset;cursor:pointer;display:block;position:relative;--beak:0;-webkit-tap-highlight-color:transparent;
  --px-o:color-mix(in srgb,var(--ui-text-primary) 97%,transparent);
  --px-d:color-mix(in srgb,var(--ui-accent) 18%,color-mix(in srgb,var(--ui-text-primary) 80%,var(--ui-bg-editor,transparent)));
  --px-r:color-mix(in srgb,var(--ui-accent) 24%,color-mix(in srgb,var(--ui-text-primary) 64%,var(--ui-bg-editor,transparent)));
  --px-M:color-mix(in srgb,var(--ui-text-primary) 90%,var(--ui-bg-editor,transparent));
  --px-m:color-mix(in srgb,var(--ui-accent) 22%,color-mix(in srgb,var(--ui-text-primary) 70%,var(--ui-bg-editor,transparent)));
  --px-p:color-mix(in srgb,var(--ui-text-primary) 86%,var(--ui-bg-editor,transparent));
  --px-h:color-mix(in srgb,var(--ui-accent) 40%,color-mix(in srgb,var(--ui-text-primary) 50%,var(--ui-bg-editor,transparent)));
  --px-H:color-mix(in srgb,var(--ui-purple) 40%,color-mix(in srgb,var(--ui-text-primary) 52%,var(--ui-bg-editor,transparent)));
  --px-y:color-mix(in srgb,var(--ui-text-primary) 66%,var(--ui-bg-editor,transparent));
  --px-Y:color-mix(in srgb,var(--ui-text-primary) 84%,var(--ui-bg-editor,transparent));
  --px-e:var(--ui-bg-editor,#fff);--px-w:color-mix(in srgb,var(--ui-bg-editor,#fff) 94%,var(--ui-text-primary));
  --px-g:color-mix(in srgb,var(--ui-text-primary) 44%,var(--ui-bg-editor,transparent));
  --px-l:color-mix(in srgb,var(--ui-text-primary) 76%,var(--ui-bg-editor,transparent));
  --px-R:color-mix(in srgb,var(--ui-red) 88%,var(--ui-text-primary));
  --px-c:var(--accent);--px-C:color-mix(in srgb,var(--accent) 62%,var(--ui-text-primary));--px-k:color-mix(in srgb,var(--accent) 28%,var(--ui-bg-editor,#fff))}
:root.dark .fkb{
  --px-o:color-mix(in srgb,var(--ui-accent) 5%,var(--ui-bg-editor,#000));
  --px-d:color-mix(in srgb,var(--ui-accent) 20%,color-mix(in srgb,var(--ui-text-primary) 15%,var(--ui-bg-editor,#000)));
  --px-r:color-mix(in srgb,var(--ui-accent) 30%,color-mix(in srgb,var(--ui-text-primary) 34%,var(--ui-bg-editor,#000)));
  --px-M:color-mix(in srgb,var(--ui-accent) 14%,color-mix(in srgb,var(--ui-text-primary) 9%,var(--ui-bg-editor,#000)));
  --px-m:color-mix(in srgb,var(--ui-accent) 26%,color-mix(in srgb,var(--ui-text-primary) 23%,var(--ui-bg-editor,#000)));
  --px-p:color-mix(in srgb,var(--ui-accent) 16%,color-mix(in srgb,var(--ui-text-primary) 12%,var(--ui-bg-editor,#000)));
  --px-h:color-mix(in srgb,var(--ui-accent) 46%,color-mix(in srgb,var(--ui-text-primary) 40%,var(--ui-bg-editor,#000)));
  --px-H:color-mix(in srgb,var(--ui-purple) 46%,color-mix(in srgb,var(--ui-text-primary) 34%,var(--ui-bg-editor,#000)));
  --px-y:color-mix(in srgb,var(--ui-text-primary) 46%,var(--ui-bg-editor,#000));
  --px-Y:color-mix(in srgb,var(--ui-text-primary) 26%,var(--ui-bg-editor,#000));
  --px-e:color-mix(in srgb,var(--ui-text-primary) 94%,transparent);--px-w:color-mix(in srgb,var(--ui-text-primary) 88%,transparent);
  --px-g:color-mix(in srgb,var(--ui-text-primary) 40%,var(--ui-bg-editor,#000));
  --px-l:color-mix(in srgb,var(--ui-text-primary) 48%,var(--ui-bg-editor,#000));
  --px-k:color-mix(in srgb,var(--accent) 35%,var(--ui-text-primary));--px-i:color-mix(in srgb,var(--ui-text-primary) 95%,#fff);--px-q:color-mix(in srgb,var(--ui-yellow) 72%,var(--ui-text-primary))}
.fkb .p-o{fill:var(--px-o)}.fkb .p-d{fill:var(--px-d)}.fkb .p-r{fill:var(--px-r)}.fkb .p-M{fill:var(--px-M)}
.fkb .p-m{fill:var(--px-m)}.fkb .p-p{fill:var(--px-p)}.fkb .p-h{fill:var(--px-h)}.fkb .p-H{fill:var(--px-H)}
.fkb .p-y{fill:var(--px-y)}.fkb .p-Y{fill:var(--px-Y)}.fkb .p-e{fill:var(--px-e)}.fkb .p-w{fill:var(--px-w)}
.fkb .p-g{fill:var(--px-g)}.fkb .p-l{fill:var(--px-l)}.fkb .p-R{fill:var(--px-R)}
.fkb .p-c{fill:var(--px-c)}.fkb .p-C{fill:var(--px-C)}.fkb .p-k{fill:var(--px-k)}
.fkb .fx .p-\\#{fill:var(--px-c)}.fkb .fx-zzz .p-\\#{fill:var(--px-y)}.fkb .fx-sparkle .p-\\#{fill:var(--px-k)}
.fkb:focus-visible{outline:2px solid var(--ui-accent);outline-offset:4px;border-radius:8px}
.fkb-svg{width:100%;height:100%;overflow:visible;display:block}
.fkb-frame-stack{position:relative;display:block;width:100%;height:100%;image-rendering:pixelated}
.fkb-frame{position:absolute;inset:0;width:100%;height:100%;image-rendering:pixelated;object-fit:fill}
.fkb-frame.b-caw,.fkb-frame.b-lid,.fkb-frame.b-wingup{opacity:0}
.fkb .fkb-frame.b-shut{opacity:1}
.fkb .fkb-frame.b-caw{opacity:clamp(0,calc((var(--beak) - .3) * 100),1)}
.fkb .fkb-frame.b-shut{opacity:clamp(0,calc((.3 - var(--beak)) * 100 + 1),1)}
.fkb .fkb-frame.b-lid{animation:fkb-blink var(--blink) steps(1) var(--phase) infinite}
.fkb .fkb-frame.b-wingup{animation:none}
.fkb[data-state="muted"] .fkb-frame.b-shut{opacity:0!important}
.fkb[data-state="muted"] .fkb-frame.b-lid{opacity:1!important;animation:none}
.fkb-particles{position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none}
.fkb g{transform-box:view-box}
/* beak: caw on notes, big caw tips the head back a pixel */
.fkb .b-caw{opacity:clamp(0,calc((var(--beak) - .3) * 100),1)}
.fkb .b-shut{opacity:clamp(0,calc((.3 - var(--beak)) * 100 + 1),1)}
.fkb .b-tilt{transform:translate(calc(clamp(0,(var(--beak) - .7) * 100,1) * -1px),calc(clamp(0,(var(--beak) - .7) * 100,1) * -1px))}
.fkb .b-lid{opacity:0;animation:fkb-blink var(--blink) steps(1) var(--phase) infinite}
.fkb .b-wingup{opacity:0}
/* two-frame costume loops */
.fkb .c-b{opacity:0;animation:fkb-alt-b .9s steps(1) var(--phase) infinite}
.fkb .c-a{animation:fkb-alt-a .9s steps(1) var(--phase) infinite}
.fkb[data-state="singing"] .c-a{animation-duration:calc(var(--beat) / 1)}
.fkb[data-state="singing"] .c-b{animation-duration:calc(var(--beat) / 1)}
.fkb[data-gesture="bounce"][data-state="singing"] .c-a,.fkb[data-gesture="bounce"][data-state="singing"] .c-b{animation-duration:.16s}
/* particles: notes when singing, Z's when dozing or muted, sparkles near shiny things */
.fkb .fx-p{opacity:0}
.fkb[data-state="singing"] .fx-notes .fx-p{animation:fkb-rise calc(var(--beat) * 2) steps(6) infinite}
.fkb[data-state="singing"] .fx-notes .fx-p1{animation-delay:calc(var(--beat) * .66)}
.fkb[data-state="singing"] .fx-notes .fx-p2{animation-delay:calc(var(--beat) * 1.33)}
.fkb:not([data-state="singing"]) .fx-zzz .fx-p,.fkb[data-state="muted"] .fx-zzz .fx-p{animation:fkb-rise 3.6s steps(8) infinite}
.fkb .fx-zzz .fx-p1{animation-delay:1.2s}.fkb .fx-zzz .fx-p2{animation-delay:2.4s}
.fkb .fx-sparkle .fx-p{animation:fkb-spark 2.8s steps(1) var(--phase) infinite}
.fkb .fx-sparkle .fx-p1{animation-delay:.9s}.fkb .fx-sparkle .fx-p2{animation-delay:1.8s}
/* idle: whole-pixel, stepped like a real sprite */
.fkb .b-body{animation:fkb-breathe var(--breath) steps(1) var(--phase) infinite}
.fkb[data-gesture="nod"] .b-head,.fkb[data-gesture="regal"] .b-head{animation:fkb-nod calc(var(--beat) * 2) steps(1) var(--phase) infinite}
.fkb[data-gesture="lean"] .b-root{animation:fkb-lean 3.2s steps(1) var(--phase) infinite}
.fkb[data-gesture="tap"] .b-wing{animation:fkb-tap calc(var(--beat) * 2) steps(1) var(--phase) infinite}
.fkb[data-gesture="sway"] .b-root{animation:fkb-sway 4s steps(1) var(--phase) infinite}
.fkb[data-gesture="tilt"] .b-head{animation:fkb-peek 5s steps(1) var(--phase) infinite}
.fkb[data-gesture="doze"] .b-head{animation:fkb-droop 5s steps(1) var(--phase) infinite}
.fkb[data-gesture="settle"] .b-wing{animation:fkb-tap 6s steps(1) var(--phase) infinite}
.fkb[data-gesture="twitch"] .b-head{animation:fkb-twitch 2.4s steps(1) var(--phase) infinite}
.fkb[data-gesture="bounce"] .b-root{animation:fkb-bob 2.2s steps(1) var(--phase) infinite}
.fkb[data-gesture="answer"] .b-head{animation:fkb-peek 4s steps(1) var(--phase) infinite}
/* singing: gestures lock to the beat */
.fkb[data-state="singing"] .b-head{animation:fkb-nod var(--beat) steps(1) infinite}
.fkb[data-state="singing"][data-gesture="hop"] .b-root{animation:fkb-hop calc(var(--beat) * 2) steps(1) infinite}
.fkb[data-state="singing"][data-gesture="bounce"] .b-root{animation:fkb-bob var(--beat) steps(1) infinite}
.fkb[data-state="singing"][data-gesture="tap"] .b-wing{animation:fkb-tap var(--beat) steps(1) infinite}
.fkb[data-state="singing"][data-gesture="twitch"] .b-head{animation:fkb-twitch calc(var(--beat) * 2) steps(1) infinite}
.fkb[data-state="singing"][data-gesture="belt"] .b-head{animation:fkb-belt calc(var(--beat) * 4) steps(1) infinite}
.fkb[data-state="singing"][data-gesture="lean"] .b-root{animation:fkb-lean calc(var(--beat) * 2) steps(1) infinite}
/* muted / dimmed */
.fkb[data-state="muted"] .b-lid{opacity:1;animation:none}
.fkb[data-state="muted"] .b-head{animation:none;transform:translateY(1px)}
.fkb[data-state="muted"] .c-costume{opacity:.45}
.fkb[data-state="dim"]{opacity:.3;filter:saturate(.3)}
.fkb{transition:opacity .12s,filter .12s}
/* arrivals and departures: the real wing-up frame flaps, then folds */
.fkb[data-anim="land"] .b-root{animation:fkb-land .64s steps(8,end) var(--land-delay,0ms) both!important}
.fkb[data-anim="land"] .b-wingup{animation:fkb-wingup .64s steps(1) var(--land-delay,0ms) both!important}
.fkb[data-anim="land"] .b-wing{animation:fkb-wingfold .64s steps(1) var(--land-delay,0ms) both!important}
.fkb[data-anim="leave"] .b-root{animation:fkb-leave .4s steps(6,end) both!important}
.fkb[data-anim="leave"] .b-wingup{animation:fkb-wingup .4s steps(1) both reverse!important}
.fkb[data-anim="leave"] .b-wing{opacity:0}
.fkb[data-anim="ruffle"] .b-body{animation:fkb-ruffle .24s steps(1) both!important}

@keyframes fkb-blink{0%,94%{opacity:0}95%,98%{opacity:1}99%,100%{opacity:0}}
@keyframes fkb-alt-a{0%,49%{opacity:1}50%,100%{opacity:0}}
@keyframes fkb-alt-b{0%,49%{opacity:0}50%,100%{opacity:1}}
@keyframes fkb-rise{0%{opacity:0;transform:none}12%{opacity:1}80%{opacity:1;transform:translate(1px,-5px)}100%{opacity:0;transform:translate(2px,-7px)}}
@keyframes fkb-spark{0%,70%,100%{opacity:0}74%,82%{opacity:1}}
@keyframes fkb-breathe{0%,49%{transform:none}50%,100%{transform:translateY(-.5px)}}
@keyframes fkb-nod{0%,49%{transform:none}50%,100%{transform:translateY(1px)}}
@keyframes fkb-droop{0%,59%{transform:translateY(1px)}60%,72%{transform:none}73%,100%{transform:translateY(1px)}}
@keyframes fkb-lean{0%,49%{transform:none}50%,100%{transform:translateX(-1px)}}
@keyframes fkb-tap{0%,79%{transform:none}80%,100%{transform:translateY(-1px)}}
@keyframes fkb-sway{0%,24%{transform:none}25%,49%{transform:translateX(1px)}50%,74%{transform:none}75%,100%{transform:translateX(-1px)}}
@keyframes fkb-peek{0%,64%{transform:none}65%,89%{transform:translate(1px,-1px)}90%,100%{transform:none}}
@keyframes fkb-twitch{0%{transform:none}20%{transform:translateX(1px)}35%{transform:none}55%{transform:translateY(1px)}70%{transform:translate(1px,0)}85%{transform:none}}
@keyframes fkb-bob{0%,49%{transform:none}50%,100%{transform:translateY(-1px)}}
@keyframes fkb-hop{0%,14%{transform:translateY(-3px)}15%,24%{transform:translateY(-1px)}25%,100%{transform:none}}
@keyframes fkb-belt{0%,24%{transform:translate(-1px,-2px)}25%,100%{transform:none}}
@keyframes fkb-land{0%{transform:translate(22px,-26px);opacity:0}10%{opacity:1}80%{transform:translate(0,1px)}100%{transform:none}}
@keyframes fkb-wingup{0%,12%{opacity:1;transform:none}13%,25%{opacity:1;transform:translateY(3px)}26%,38%{opacity:1;transform:none}39%,51%{opacity:1;transform:translateY(3px)}52%,70%{opacity:1;transform:none}71%,100%{opacity:0}}
@keyframes fkb-wingfold{0%,70%{opacity:0}71%,100%{opacity:1}}
@keyframes fkb-leave{0%{transform:none}20%{transform:translateY(1px)}100%{transform:translate(-24px,-28px);opacity:0}}
@keyframes fkb-ruffle{0%,49%{transform:translateY(-1px)}50%,100%{transform:none}}
@media (prefers-reduced-motion:reduce){.fkb *{animation:none!important}.fkb .b-lid,.fkb .fx-p,.fkb .b-wingup,.fkb .c-b{opacity:0}}
`
