// Pure renderer for story.json v2 (docs/design.md 2.2-2.4).
// The state blob is the single source of truth: applyTransition produces a
// new blob, render only ever reads one.

const storyContainer = document.getElementById("story-container");
const weatherCanvas = document.getElementById("weather-canvas");
const effectOverlay = document.getElementById("effect-overlay");

let config;
let colours;
let storyData;

// state after entering each path index; the last entry is the live state
let currentState;
let stepStates = [];

// ---- state blob (design 2.2) ---------------------------------------------
const MAX_STRING = 500; // URL bloat guard for string vars

function emptyState() {
    return {
        v: 2,
        path: [],
        variants: [],
        vars: {},
        visits: {},
        used: [],
        rng: { seed: 0, n: 0 },
        call: [],
        povColours: {},
    };
}

// a shared link can be stale or hand edited, never trust its shape; v must
// equal 2 or the state is refused (old v1 URLs are not migrated)
function sanitizeState(state) {
    if (!state || typeof state !== "object" || Array.isArray(state)) return emptyState();
    if (state.v !== 2) return emptyState();

    const path = [];
    if (Array.isArray(state.path)) {
        for (const node of state.path) {
            if (typeof node !== "string") break;
            path.push(node);
        }
    }

    const variants = Array.isArray(state.variants)
        ? state.variants.slice(0, path.length).map(v => (Number.isInteger(v) && v >= 0 ? v : null))
        : [];

    const vars = {};
    if (state.vars && typeof state.vars === "object" && !Array.isArray(state.vars)) {
        for (const [key, value] of Object.entries(state.vars)) {
            if (typeof key !== "string") continue;
            if (typeof value === "number" && isFinite(value)) vars[key] = value;
            else if (typeof value === "boolean") vars[key] = value;
            else if (typeof value === "string") vars[key] = value.slice(0, MAX_STRING);
        }
    }

    const visits = {};
    if (state.visits && typeof state.visits === "object" && !Array.isArray(state.visits)) {
        for (const [key, value] of Object.entries(state.visits)) {
            if (typeof key === "string" && Number.isInteger(value) && value > 0) visits[key] = value;
        }
    }

    const used = Array.isArray(state.used) ? state.used.filter(u => typeof u === "string") : [];

    const rng = { seed: 0, n: 0 };
    if (state.rng && typeof state.rng === "object") {
        if (Number.isInteger(state.rng.seed)) rng.seed = state.rng.seed;
        if (Number.isInteger(state.rng.n) && state.rng.n >= 0) rng.n = state.rng.n;
    }

    const call = Array.isArray(state.call) ? state.call.filter(c => typeof c === "string") : [];

    const povColours = {};
    if (state.povColours && typeof state.povColours === "object" && !Array.isArray(state.povColours)) {
        for (const [key, value] of Object.entries(state.povColours)) {
            if (typeof key === "string" && typeof value === "string") povColours[key] = value;
        }
    }

    return { v: 2, path, variants, vars, visits, used, rng, call, povColours };
}

// UTF-8 safe base64: string vars can hold any characters
function encodeState(state) {
    const bytes = new TextEncoder().encode(JSON.stringify(state));
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    return btoa(binary);
}

function decodeState(encoded) {
    const binary = atob(encoded);
    const bytes = Uint8Array.from(binary, ch => ch.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
}

function loadStateFromURL() {
    const params = new URLSearchParams(window.location.search);
    const encodedState = params.get("state");
    if (!encodedState) return emptyState();
    try {
        return sanitizeState(decodeState(encodedState));
    } catch {
        return emptyState();
    }
}

function saveStateToURL(state) {
    const url = new URL(window.location);
    url.searchParams.set("state", encodeState(state));
    // push, not replace: the reader expects the browser Back button to undo
    // the choice they just made
    window.history.pushState(null, "", url);
    updateBackButton();
}

// ---- seeded rng (design 2.2) ---------------------------------------------
// one counter drives variant picks, pov colours and dice rolls, so a save or
// a shared link reproduces the same story

function rngValue(state) {
    state.rng.n += 1;
    let x = (state.rng.seed ^ Math.imul(state.rng.n, 0x9e3779b9)) >>> 0;
    x = Math.imul(x ^ (x >>> 16), 0x85ebca6b) >>> 0;
    x = Math.imul(x ^ (x >>> 13), 0xc2b2ae35) >>> 0;
    return ((x ^ (x >>> 16)) >>> 0) / 4294967296;
}

function newSeed() {
    return Math.floor(Math.random() * 0x7fffffff);
}

function hash32(...parts) {
    let h = 0x811c9dc5;
    for (const part of parts) {
        const text = String(part);
        for (let i = 0; i < text.length; i++) {
            h ^= text.charCodeAt(i);
            h = Math.imul(h, 0x01000193);
        }
        h ^= 0xff;
        h = Math.imul(h, 0x01000193);
    }
    return h >>> 0;
}

// deterministic permutation: same seed and line always shuffle the same way
function shuffleOrder(seed, nodeId, lineIndex, length) {
    const order = Array.from({ length }, (_, i) => i);
    order.sort((a, b) => hash32(seed, nodeId, lineIndex, a) - hash32(seed, nodeId, lineIndex, b));
    return order;
}

// ---- conditions (design 1.4): one evaluator, four levels -------------------

function evalCond(cond, state) {
    if (!cond) return true;
    switch (cond.op) {
        case "truth":
            return Boolean(state.vars[cond.name]);
        case "not":
            return !evalCond(cond.arg, state);
        case "and":
            return cond.args.every(arg => evalCond(arg, state));
        case "or":
            return cond.args.some(arg => evalCond(arg, state));
        case "cmp": {
            const lhs = condSide(cond.lhs, state);
            const rhs = condSide(cond.rhs, state);
            switch (cond.cmp) {
                case ">=": return lhs >= rhs;
                case "<=": return lhs <= rhs;
                case ">": return lhs > rhs;
                case "<": return lhs < rhs;
                case "==": return lhs === rhs;
                case "!=": return lhs !== rhs;
            }
            return false;
        }
        case "visits":
            return state.visits[cond.id] || 0;
        case "count": {
            const hits = cond.args.filter(arg => evalCond(arg, state)).length;
            return hits >= cond.min && (cond.max === null || hits <= cond.max);
        }
        default:
            return false; // "bad" never renders: condition_syntax fails the build
    }
}

// plain string = var reference, {"str": ...} = literal, visits() = a number
function condSide(side, state) {
    if (typeof side === "number" || typeof side === "boolean") return side;
    if (typeof side === "string") return state.vars[side] ?? 0;
    if (side && typeof side === "object" && "str" in side) return side.str;
    return evalCond(side, state);
}

// ---- effects (design 1.5): the only writer of state ------------------------

function applyEffect(effect, state) {
    switch (effect.op) {
        case "set":
            state.vars[effect.name] = true;
            break;
        case "clear":
            delete state.vars[effect.name];
            break;
        case "assign":
            state.vars[effect.name] = effect.val;
            break;
        case "add":
            state.vars[effect.name] = (Number(state.vars[effect.name]) || 0) + effect.val;
            break;
        case "roll": {
            const [count, sides, modifier] = effect.dice;
            let total = modifier;
            for (let i = 0; i < count; i++) total += 1 + Math.floor(rngValue(state) * sides);
            state.vars[effect.var] = total;
            break;
        }
        case "unlock":
            break; // achievements arrive with the meta work (P3)
    }
}

// ---- pov colours -----------------------------------------------------------

// find the canonically cased key for a pov, so "You" and "you" share a colour
function povKey(pov, existing) {
    if (!pov || !config.povCaseInsensitive) return pov;
    const match = Object.keys(existing).find(key => key.toLowerCase() === pov.toLowerCase());
    return match || pov;
}

function assignPovColour(state, pov, partpov) {
    if (!pov) return;
    const key = povKey(pov, state.povColours);
    if (state.povColours[key]) return;

    const used = Object.values(state.povColours);
    let pool = colours.filter(col => !used.includes(col));
    if (!pool.length) pool = colours;

    const partkey = partpov ? povKey(partpov, state.povColours) : null;
    if (partkey && state.povColours[partkey]) {
        const contrasting = pool.filter(col => contrast(col, state.povColours[partkey]) >= 10);
        if (contrasting.length) pool = contrasting;
    }

    state.povColours[key] = pool[Math.floor(rngValue(state) * pool.length)];
}

// a pov the transition walk never saw (stale link) still needs a colour;
// hash-picked so the same name always lands on the same one, with no mutation
function povColourFor(state, pov) {
    const key = povKey(pov, state.povColours);
    if (state.povColours[key]) return state.povColours[key];
    if (config.povColours) {
        const configured = povKey(pov, config.povColours);
        if (config.povColours[configured]) return config.povColours[configured];
    }
    return colours[hash32(key) % colours.length];
}

// ---- alt branches (design 1.6) --------------------------------------------
// seq keys off the visit number, cycle wraps, shuffle permutes without a
// repeat until exhausted; all pure functions of the state blob

function pickAltBranch(token, state, nodeId, visitNumber, lineIndex) {
    const branches = token.branches;
    if (!branches.length) return [];
    let index;
    if (token.mode === "cycle") {
        index = visitNumber % branches.length;
    } else if (token.mode === "shuffle") {
        const order = shuffleOrder(state.rng.seed, nodeId, lineIndex, branches.length);
        index = order[visitNumber % branches.length];
    } else {
        index = Math.min(visitNumber, branches.length - 1);
    }
    return branches[index] || [];
}

// walk a token stream the way the renderer will: evaluate ifs, pick alts,
// hand every marker to onToken (design 2.3 step 4 uses this for pov colours)
function walkTokens(tokens, state, nodeId, visitNumber, lineIndex, onToken) {
    for (const token of tokens) {
        switch (token.t) {
            case "mk":
                onToken(token);
                break;
            case "if": {
                const branch = evalCond(token.cond, state) ? token.then : token.else;
                for (const entry of branch) {
                    walkTokens(entry, state, nodeId, visitNumber, lineIndex, onToken);
                }
                break;
            }
            case "alt": {
                const branch = pickAltBranch(token, state, nodeId, visitNumber, lineIndex);
                for (const entry of branch) {
                    walkTokens(entry, state, nodeId, visitNumber, lineIndex, onToken);
                }
                break;
            }
            default:
                break; // lit and var carry no markers
        }
    }
}

function walkLineList(lines, state, nodeId, visitNumber, onToken) {
    for (let lineIndex = 0; lineIndex < lines.length; lineIndex++) {
        const entry = lines[lineIndex];
        if (entry.length === 1 && entry[0].t === "if") {
            // block form: only the taken branch is ever visible
            const branch = evalCond(entry[0].cond, state) ? entry[0].then : entry[0].else;
            walkLineList(branch, state, nodeId, visitNumber, onToken);
        } else {
            walkTokens(entry, state, nodeId, visitNumber, lineIndex, onToken);
        }
    }
}

// every pov a visible line will name gets its colour assigned once, from the
// seeded rng, while the node is entered (design 2.3 step 4)
function assignVisiblePovs(state, node, variant, nodeId) {
    const seen = new Set();
    const consider = pov => {
        if (!pov || seen.has(pov)) return;
        seen.add(pov);
        assignPovColour(state, pov, variant.pov);
    };
    consider(variant.pov);
    consider(variant.messagepov);
    const visitNumber = state.visits[nodeId] || 0; // pre-increment: this visit
    walkLineList(variant.lines, state, nodeId, visitNumber, token => {
        if (token.k === "pov" || token.k === "message" || token.k === "messageUnsent") {
            consider(token.v);
        }
    });
}

// ---- flow (design 2.3) -----------------------------------------------------

// the choices on screen right now: gated by conditions, revisit, and by a
// live `next` (an auto-continuing node never surfaces its choices)
function visibleChoices(state, node, variant, path, index) {
    if (liveNext(state, node)) return [];
    return (variant.choices || []).filter(choice => {
        if (choice.if && !evalCond(choice.if, state)) return false;
        const target = storyData.nodes[choice.to];
        if (!target) return true; // unimplemented, sure, let it show
        const alreadyVisited = path.slice(0, index + 1).includes(choice.to);
        return !alreadyVisited || target.revisit;
    });
}

function liveNext(state, node) {
    return Boolean(node.next && !node.end && (!node.nextIf || evalCond(node.nextIf, state)));
}

// a stored variant index wins; anything stale falls back to the first variant
function nodeVariant(node, index) {
    if (Number.isInteger(index) && index >= 0 && index < node.variants.length) {
        return node.variants[index];
    }
    return node.variants[0] || { lines: [], choices: [] };
}

// append a node to the path and run its fresh-entry work (design 2.3 step 4)
function enterNode(state, nodeId) {
    state.path.push(nodeId);
    const node = storyData.nodes[nodeId];
    if (!node) {
        state.variants.push(null); // the validator warns; render shows a placeholder
        return;
    }

    let pick = 0;
    if (node.variants.length > 1) {
        pick = Math.floor(rngValue(state) * node.variants.length);
    }
    state.variants.push(pick);

    const variant = node.variants[pick];
    if (variant.effects) {
        for (const effect of variant.effects) applyEffect(effect, state);
    }

    assignVisiblePovs(state, node, variant, nodeId);

    state.visits[nodeId] = (state.visits[nodeId] || 0) + 1;
}

// the one place state changes: pure with respect to the caller's blob
function applyTransition(state, action) {
    const next = structuredClone(state);
    // a snapshot per entered node so the renderer can draw each step from the
    // state exactly as it was right after that step's entry
    const steps = [];
    const enter = nodeId => {
        enterNode(next, nodeId);
        steps.push({ index: next.path.length - 1, nodeId, state: structuredClone(next) });
    };

    if (action.type === "start") {
        next.path = [];
        next.variants = [];
        next.vars = {};
        next.visits = {};
        next.used = [];
        next.call = [];
        next.povColours = { ...(config.povColours || {}) };
        next.rng = { seed: action.seed ?? newSeed(), n: 0 };
        const starts = Object.keys(storyData.nodes).filter(id => storyData.nodes[id].start);
        if (!starts.length) error("No starting story nodes defined");
        // a replay can name the start node; a fresh run picks at random
        const nodeId = action.node || starts[Math.floor(Math.random() * starts.length)];
        enter(nodeId);
        return { state: next, steps };
    }

    if (action.type === "restart") {
        return applyTransition(emptyState(), { type: "start" });
    }

    if (action.type === "choice" || action.type === "advance") {
        const nodeId = next.path[next.path.length - 1];
        const node = storyData.nodes[nodeId];
        if (!node) return { state: next, steps: [] };
        const variant = nodeVariant(node, next.variants[next.variants.length - 1]);

        // next is unconditional: it wins over any choices on the node
        if (action.type === "advance" && liveNext(state, node)) {
            enter(node.next);
            return { state: next, steps };
        }

        const visible = visibleChoices(next, node, variant, next.path, next.path.length - 1);
        let choice = null;
        if (action.type === "advance") {
            if (visible.length === 1) choice = visible[0];
        } else {
            choice = visible[action.index];
        }
        if (!choice) return { state: next, steps: [] };

        if (choice.effects) {
            for (const effect of choice.effects) applyEffect(effect, next);
        }
        enter(choice.to);
        return { state: next, steps };
    }

    return { state: next, steps: [] };
}

// rebuild the state after every step of a shared link or a save: same seed,
// same choices, so variant picks and pov colours re-derive exactly
function computeStepStates(target) {
    if (!target.path.length) return [];
    const states = [];
    let current = applyTransition(emptyState(), {
        type: "start",
        node: target.path[0],
        seed: target.rng.seed,
    }).state;
    states.push(current);

    for (let i = 1; i < target.path.length; i++) {
        const prevId = current.path[current.path.length - 1];
        const node = storyData.nodes[prevId];
        let result = null;
        if (node && liveNext(current, node) && node.next === target.path[i]) {
            result = applyTransition(current, { type: "advance" });
        } else if (node) {
            const variant = nodeVariant(node, current.variants[current.variants.length - 1]);
            const visible = visibleChoices(current, node, variant, current.path, current.path.length - 1);
            // first visible choice leading to the recorded target; choice
            // effects are identical across same-target choices (design 1.3)
            const index = visible.findIndex(choice => choice.to === target.path[i]);
            if (index >= 0) result = applyTransition(current, { type: "choice", index });
        }
        if (!result || !result.steps.length) break; // stale link: render as far as it still makes sense
        current = result.state;
        states.push(current);
    }
    return states;
}

// ---- visual machinery (design 2.4: the unchanged surface) ------------------

function keepView() {
    window.scrollTo({
        top: document.body.scrollHeight,
        behavior: motionReduced() ? "auto" : "smooth"
    });
}

async function loadConfig() {
    let configText;
    try {
        let res = await fetch("config.yaml");
        if (!res.ok) throw new Error("config.yaml not found");
        configText = await res.text();
    } catch {
        let res = await fetch("../config.yaml");
        if (!res.ok) throw new Error("No config.yaml found");
        configText = await res.text();
    }

    if (!configText.trim()) {
        throw new Error("Config file is empty");
    }

    config = jsyaml.load(configText);
}

// theme.* in config.yaml is the author's styling block; fold it into the
// legacy top-level keys so the rest of the engine keeps one source of truth
function applyTheme() {
    const theme = config.theme || {};
    config.textColour = theme.textColour ?? config.textColour ?? "#e8e6e3";
    config.darkTextColour = theme.darkTextColour ?? config.darkTextColour ?? "#1b1b1f";
    config.backgroundColour = theme.backgroundColour ?? config.backgroundColour ?? "#0e0e12";
    config.accentColour = theme.accentColour ?? config.redoButtonColour ?? "#0a84ff";
    config.povStyle = theme.povStyle === "box" ? "box" : "header";

    const root = document.documentElement.style;
    root.setProperty("--text", config.textColour);
    root.setProperty("--dark-text", config.darkTextColour);
    root.setProperty("--bg", config.backgroundColour);
    root.setProperty("--accent", config.accentColour);
    if (theme.font) root.setProperty("--font", theme.font);
    if (theme.uiFont) root.setProperty("--ui-font", theme.uiFont);
    if (theme.cornerRadius) root.setProperty("--radius", theme.cornerRadius);
}

// the named colour list feeds pov assignment; marker matching now happens at
// build time, so the runtime keeps no marker regexes (design 2.4)
async function loadColours() {
    const text = await fetch("named_colours").then(r => r.text());
    colours = text.toLowerCase().split(/\r?\n/).filter(Boolean);
}

// bumped whenever the view is cleared so an in-flight render can notice it
// has been superseded and stop rather than appending to a wiped container
let renderGeneration = 0;

// every timed wait funnels through here so Skip can cut them short
let skipMode = false;
const pendingWaits = new Set();

function wait(ms) {
    if (skipMode) return Promise.resolve();
    return new Promise(resolve => {
        const entry = {};
        entry.timer = setTimeout(finish, ms);
        function finish() {
            clearTimeout(entry.timer);
            pendingWaits.delete(entry);
            resolve();
        }
        entry.finish = finish;
        pendingWaits.add(entry);
    });
}

function triggerSkip() {
    skipMode = true;
    for (const entry of [...pendingWaits]) entry.finish();
}

// recorded as lines render, replayed when the history panel opens
let storyHistory = [];

// true while a node's lines are still fading in, so a click can fast-forward
// the reveal instead of advancing the story
let textRevealing = false;

// pending auto-follow of a linear node's only choice; cancelled the moment
// the reader interacts so it never races their own click
let autoAdvanceTimer = null;

function cancelAutoAdvance() {
    if (autoAdvanceTimer) {
        clearTimeout(autoAdvanceTimer);
        autoAdvanceTimer = null;
    }
}

// helper functions
const statusEl = document.getElementById("status");
const statusText = document.getElementById("status-text");
const statusRetry = document.getElementById("status-retry");

// the page used to sit blank whenever a fetch failed, with only a console
// error to explain it
function showStatus(message, retry = null) {
    statusText.textContent = message;
    statusRetry.hidden = !retry;
    statusRetry.onclick = retry;
    statusEl.hidden = false;
}

function hideStatus() {
    statusEl.hidden = true;
}

function error(message) {
    showStatus(message, () => window.location.reload());
    throw new Error(message);
}

// honoured live so a reader can flip the OS setting without reloading
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

// Render the components
async function fadeText(element) {
    const speed = parseFloat(element.dataset.speed);
    const fadeDuration = parseFloat(config.fadeDuration) * (speed / config.textSpeed);
    const computedOpacity = parseFloat(getComputedStyle(element).opacity) || 1;
    keepView();

    // keep the pacing, drop the animation
    if (motionReduced()) {
        element.style.opacity = computedOpacity;
        await wait(speed);
        return;
    }

    element.style.opacity = 0;
    element.style.transition = `opacity ${fadeDuration}ms ease`;
    element.getBoundingClientRect();

    requestAnimationFrame(() => element.style.opacity = computedOpacity);
    await wait(Math.max(speed, fadeDuration));
}

function toMillis(speed) {
    if (speed.endsWith("ms")) {
        return parseFloat(speed.replace("ms", "").trim());
    } else if (speed.endsWith("s")) {
        return 1000 * parseFloat(speed.replace("s", "").trim());
    }
}

function parsePaceMultiplier(pace) {
    if (!pace) {
        return 1;
    }

    pace = pace.replace("pace", "");

    const cleanpace = pace.replace("ms", "").replace("s", "").trim();
    const isNumber = cleanpace !== "" && isFinite(cleanpace);

    if (isNumber) {
        return toMillis(pace) / config.textSpeed;
    }

    return config.paceMultipliers[pace] || 1;
}

function parseColor(color) {
    const ctx = document.createElement("canvas").getContext("2d");
    ctx.fillStyle = color;
    let c = ctx.fillStyle;

    // if hex, convert to r,g,b
    if (c[0] === "#") {
        if (c.length === 4) { // #rgb
            return [
                parseInt(c[1] + c[1], 16),
                parseInt(c[2] + c[2], 16),
                parseInt(c[3] + c[3], 16)
            ];
        }
        return [
            parseInt(c[1] + c[2], 16),
            parseInt(c[3] + c[4], 16),
            parseInt(c[5] + c[6], 16)
        ];
    }

    // if rgb(a)
    const m = c.match(/\d+/g);
    if (m) return m.slice(0, 3).map(Number);

    // fallback to white
    return [255, 255, 255];
}

function contrast(fg, bg) {
    const [r1, g1, b1] = parseColor(fg);
    const [r2, g2, b2] = parseColor(bg);

    const b1v = (r1 * 299 + g1 * 587 + b1 * 114) / 1000;
    const b2v = (r2 * 299 + g2 * 587 + b2 * 114) / 1000;

    return Math.abs(b1v - b2v);
}


function createPOVContainer(pov, state, partpov = null) {
    const povContainer = document.createElement("div");
    const povName = document.createElement("div");
    const colour = povColourFor(state, pov);

    povContainer.classList.add("story-pov");
    if (config.povStyle === "box") {
        povContainer.classList.add("pov-box");
        povContainer.style.borderColor = colour;
        povContainer.style.background = `
            linear-gradient(
                180deg,
                color-mix(in srgb, ${colour} 30%, transparent) 0%,
                color-mix(in srgb, ${colour} 10%, transparent) 100%
            )
        `;
    } else {
        // header style: a coloured heading and a hairline, no box
        povContainer.classList.add("pov-header");
        povContainer.style.borderTopColor = colour;
        povContainer.style.borderBottomColor = `color-mix(in srgb, ${colour} 35%, transparent)`;
    }

    povName.style.color = colour;
    povName.textContent = pov;
    povName.classList.add("pov-name");
    //  we might need to adjust the contrast
    const bgContrast = contrast(colour, getComputedStyle(document.body).backgroundColor);
    if (bgContrast < 60) {
        povName.style.background = `color-mix(in srgb, ${colour} 50%, white)`;
    }

    povContainer.appendChild(povName);
    return povContainer;
}

function caseCheck(pov) {
    if (!pov) { return pov; }
    return config.povCaseInsensitive ? pov.toLowerCase() : pov;
}

function adjustTextColour(obj, bgColour) {
    if (!obj.style.color) {
        if (contrast(bgColour, config.textColour) < 60) {
            obj.style.color = config.darkTextColour;
        }
    }
}

function addNewLine(part, line, pov, lastpov, lastpovcontainer, partpov, state) {
    if (pov) {
        const isPart = caseCheck(pov) === caseCheck(partpov);
        if (isPart) {
            // use the default container
            part.appendChild(line);
            return null;
        } else if (caseCheck(pov) === caseCheck(lastpov)) {
            // out pov hasn't changed
            lastpovcontainer.appendChild(line);
            return lastpovcontainer
        } else {
            // change to a new pov container
            const newpovcontainer = createPOVContainer(pov, state, !isPart ? partpov : null);
            adjustTextColour(line, newpovcontainer.style.background);
            newpovcontainer.appendChild(line);
            part.appendChild(newpovcontainer);
            return newpovcontainer
        }
    } else {
        part.appendChild(line);
        return null;
    }
}

function formatMessage(storypart, messagecontainer, messageObj, lastmsgObj, pov, lastpov, partpov, unsent, messagetitle, state) {
    const povcolour = povColourFor(state, pov);
    const mainPov = caseCheck(pov) === caseCheck(partpov);

    if (!messagecontainer) {
        messagecontainer = document.createElement("div");
        messagecontainer.classList.add("messages");
        storypart.appendChild(messagecontainer);

        if (messagetitle) {
            const titlename = document.createElement("div");
            titlename.textContent = messagetitle;
            titlename.classList.add("message-title")
            messagecontainer.appendChild(titlename)
        }
    }

    if (lastpov && caseCheck(lastpov) === caseCheck(pov)) {
        lastmsgObj.classList.add("merge-bottom");
        messageObj.classList.add("merge-top");
    } else {
        // add a name marker!
        const messageAuthor = document.createElement("div");
        messageAuthor.style.color = povcolour;
        messageAuthor.textContent = pov;
        messageAuthor.classList.add("message-author", mainPov ? "left" : "right");
        messagecontainer.appendChild(messageAuthor);
    }
    messageObj.classList.add("message", mainPov ? "left" : "right");

    if (unsent) {
        messageObj.classList.add("unsent");
        messageObj.style.background = `color-mix(in srgb, ${povcolour} 30%, transparent)`;
    } else {
        messageObj.style.background = povcolour
    }

    // update the text colour if it won't be readable
    adjustTextColour(messageObj, povcolour);

    messagecontainer.appendChild(messageObj);

    return [messagecontainer, messageObj, pov];
}

function updateWeather(weather) {
    if (weather) {
        const type = weather.toLowerCase();
        const newWeather = type === "clear" || type === "none" ? "" : `weather-${type}`;
        weatherCanvas.className = newWeather;
    }
}

function updateBackground(colour) {
    if (colour) {
        // apply the new bg colour
        document.body.style.transition = `all ${parseFloat(config.backgroundTransitionTime)}ms ease`;
        document.body.style.background = colour.replace("reset", config.backgroundColour);
        // update text to make it readable too
        document.body.style.transition = `all ${parseFloat(config.backgroundTransitionTime)}ms ease`;
        storyContainer.style.color = contrast(config.textColour, colour) > 60 ? config.textColour : config.darkTextColour;
    }
}

// ---- background image ---------------------------------------------------
const sceneImage = document.getElementById("scene-image");
let appliedImage = null;

// absent keeps whatever is showing, matching how background colours behave;
// "none" is how a node clears it
function updateImage(image) {
    if (!image) return;

    if (image === "none" || image === "reset") {
        appliedImage = null;
        sceneImage.style.opacity = 0;
        return;
    }
    if (image === appliedImage) return;
    appliedImage = image;

    if (motionReduced()) {
        sceneImage.style.backgroundImage = `url("images/${image}")`;
        sceneImage.style.opacity = 1;
        return;
    }

    // fade out, swap at the bottom, fade back in
    sceneImage.style.opacity = 0;
    const wait = parseFloat(config.fadeDuration) || 400;
    setTimeout(() => {
        if (appliedImage !== image) return; // superseded meanwhile
        sceneImage.style.backgroundImage = `url("images/${image}")`;
        sceneImage.style.opacity = 1;
    }, wait);
}

// ---- audio --------------------------------------------------------------
// two elements so a track change can crossfade instead of cutting
const bgmTracks = [new Audio(), new Audio()];
let bgmIndex = 0;
let musicName = null;
const sfxCache = new Map();

for (const track of bgmTracks) track.loop = true;

// setInterval rather than rAF: the story flow never waits on this, and a
// fade that depends on frames stalling would leave the volume wherever it was
function fadeAudio(el, to, ms, after = null) {
    const from = el.volume;
    const steps = Math.max(1, Math.round(ms / 50));
    const token = (el._fadeToken = (el._fadeToken || 0) + 1);
    let step = 0;
    const timer = setInterval(() => {
        if (el._fadeToken !== token) {
            clearInterval(timer);
            return;
        }
        step++;
        el.volume = Math.min(1, from + (to - from) * (step / steps));
        if (step >= steps) {
            clearInterval(timer);
            el.volume = to;
            if (after) after();
        }
    }, 50);
}

function updateMusic(track) {
    if (!track) return; // no music on this node: keep playing what is there

    if (track === musicName) return;

    const outgoing = bgmTracks[bgmIndex];
    fadeAudio(outgoing, 0, 400, () => outgoing.pause());

    if (track === "none" || track === "reset") {
        musicName = null;
        return;
    }

    musicName = track;
    bgmIndex = 1 - bgmIndex;
    const incoming = bgmTracks[bgmIndex];
    incoming.src = `audio/${track}`;
    incoming.volume = 0;
    // autoplay needs a gesture; readers arriving on a shared link may not
    // have given one yet, so this is allowed to fail quietly
    incoming.play().catch(() => {});
    fadeAudio(incoming, musicVolume(), 400);
}

function stopMusic() {
    musicName = null;
    for (const track of bgmTracks) fadeAudio(track, 0, 300, () => track.pause());
}

function playSfx(name) {
    let el = sfxCache.get(name);
    if (!el) {
        el = new Audio(`audio/${name}`);
        sfxCache.set(name, el);
    }
    el.volume = musicVolume();
    el.currentTime = 0;
    el.play().catch(() => {});
}

function musicVolume() {
    return settings.muted ? 0 : settings.volume;
}

function updateEffect(effectType, value) {
    const fadeTime = parseFloat(config.effectTransitionTime) || 2000;
    effectOverlay.style.transition = `--focus-size ${fadeTime}ms ease`;

    switch (effectType) {
        case "focus": {
            const percent = parseFloat(value.replace("reset", "100").replace("%", ""));
            effectOverlay.style.setProperty("--focus-size", `${percent}%`);
            break;
        }
        default:
            // reset all effects
            effectOverlay.style.setProperty("--focus-size", "105%");
            updateBackground("reset");
            break;
    }
}

// ---- token rendering (design 2.1/2.3) -------------------------------------
// the build already decided what is a marker and what is text; the renderer
// only evaluates conditions, picks alt branches, and draws what is left

// whole-line markers the lexer keeps exclusive: they never emit text
const EXCLUSIVE_MARKERS = new Set([
    "pause", "focus", "effectReset", "background", "weather", "sfx", "messageTitle",
]);

async function runMarker(token, ctx) {
    switch (token.k) {
        case "messageTitle":
            ctx.messagetitle = token.v;
            break;
        case "pause":
            await wait(toMillis(token.v));
            break;
        case "focus":
            updateEffect("focus", token.v);
            break;
        case "effectReset":
            updateEffect("effectReset", token.v);
            break;
        case "background":
            updateBackground(token.v);
            break;
        case "weather":
            updateWeather(token.v);
            break;
        case "sfx":
            playSfx(token.v);
            break;
    }
}

// one line's worth of state while its token stream is walked; first marker of
// each kind wins, matching how the old extractor consumed a raw line
function newMarks() {
    return {
        text: "",
        colour: null,
        pace: null,
        effects: [],
        pov: null,
        message: null,
        unsent: null,
    };
}

function collectToken(token, ctx, lineIndex, marks) {
    switch (token.t) {
        case "lit":
            marks.text += token.v;
            break;
        case "var":
            // unknown names stay visible as {name}, the old renderer's contract
            marks.text += token.name in ctx.state.vars
                ? String(ctx.state.vars[token.name])
                : `{${token.name}}`;
            break;
        case "if": {
            const branch = evalCond(token.cond, ctx.state) ? token.then : token.else;
            collectTokens(branch, ctx, lineIndex, marks);
            break;
        }
        case "alt": {
            const branch = pickAltBranch(token, ctx.state, ctx.nodeId, ctx.visitNumber, lineIndex);
            collectTokens(branch, ctx, lineIndex, marks);
            break;
        }
        case "mk":
            if (token.k === "colour" && marks.colour === null) marks.colour = token.v;
            else if (token.k === "pace" && marks.pace === null) marks.pace = token.v;
            else if (token.k === "effect") marks.effects.push(token.v);
            else if (token.k === "pov" && marks.pov === null) marks.pov = token.v;
            else if (token.k === "message" && marks.message === null) marks.message = token.v;
            else if (token.k === "messageUnsent" && marks.unsent === null) marks.unsent = token.v;
            break;
    }
}

function collectTokens(entries, ctx, lineIndex, marks) {
    for (const entry of entries) {
        if (entry.length === 1 && entry[0].t === "if") {
            // block form nested inside a line: only the taken branch counts
            const branch = evalCond(entry[0].cond, ctx.state) ? entry[0].then : entry[0].else;
            collectTokens(branch, ctx, lineIndex, marks);
            continue;
        }
        for (const token of entry) collectToken(token, ctx, lineIndex, marks);
    }
}

async function renderLineTokens(entry, ctx, lineIndex) {
    // a whole-line marker runs its command and emits no text
    if (entry.length === 1 && entry[0].t === "mk" && EXCLUSIVE_MARKERS.has(entry[0].k)) {
        await runMarker(entry[0], ctx);
        return;
    }

    const marks = newMarks();
    collectTokens([entry], ctx, lineIndex, marks);

    const storyLine = document.createElement("div");
    storyLine.className = "story-line";

    if (marks.colour !== null) {
        storyLine.style.color = marks.colour.replace("colour", "").replace("reset", config.textColour).trim();
    }
    if (marks.effects.length) storyLine.classList.add(...marks.effects);
    if (ctx.effectPart.length) storyLine.classList.add(...ctx.effectPart);

    // parse markdown to html; marked allows raw html through, so it goes
    // into innerHTML only after DOMPurify has stripped anything active
    storyLine.innerHTML = DOMPurify.sanitize(marked.parse(marks.text));

    storyHistory.push({ html: storyLine.innerHTML, pov: marks.pov || ctx.partpov });

    // render as a message or not
    const foundmessagepov = marks.unsent || marks.message;
    if (foundmessagepov) {
        if (!ctx.partmessagepov) ctx.partmessagepov = foundmessagepov;
        [ctx.messagescontainer, ctx.lastmessageobj, ctx.lastmessagepov] = formatMessage(
            ctx.storyPart,
            ctx.messagescontainer,
            storyLine,
            ctx.lastmessageobj,
            foundmessagepov,
            ctx.lastmessagepov,
            ctx.partmessagepov,
            marks.unsent,
            ctx.messagetitle || ctx.messageparttitle,
            ctx.state
        );
        ctx.lastpovcontainer = null;
        ctx.lastpov = null;
    } else {
        ctx.messagescontainer = null;
        ctx.lastmessageobj = null;
        ctx.lastmessagepov = null;
        ctx.messagetitle = null;
        ctx.lastpovcontainer = addNewLine(
            ctx.partpovcontainer || ctx.storyPart,
            storyLine,
            marks.pov || ctx.partpov,
            ctx.lastpov,
            ctx.lastpovcontainer,
            ctx.partpov,
            ctx.state
        );
        ctx.lastpov = marks.pov || ctx.partpov;
    }

    // ensure we wait the right amount of time between lines of text
    const speed = parsePaceMultiplier(marks.pace) * ctx.partPace * config.textSpeed;
    storyLine.dataset.speed = speed;
    await fadeText(storyLine);
}

async function renderLineList(entries, ctx) {
    for (let lineIndex = 0; lineIndex < entries.length; lineIndex++) {
        const entry = entries[lineIndex];
        if (entry.length === 1 && entry[0].t === "if") {
            // block form: only the taken branch is ever visible
            const branch = evalCond(entry[0].cond, ctx.state) ? entry[0].then : entry[0].else;
            await renderLineList(branch, ctx);
            continue;
        }
        await renderLineTokens(entry, ctx, lineIndex);
    }
}

async function renderText(nodeContainer, state, node, variant, nodeId) {
    const storyPart = document.createElement("div");
    storyPart.className = "story-part";

    nodeContainer.appendChild(storyPart);

    textRevealing = true;

    // the node colour choice
    if (variant.colour) storyPart.style.color = variant.colour;

    // the speed for this part
    const partPace = parsePaceMultiplier(variant.pace);

    // any effect classes
    const effectPart = variant.effect ? variant.effect.split() : [];

    const partpov = variant.pov;
    let partpovcontainer;
    if (partpov) {
        partpovcontainer = createPOVContainer(partpov, state);
        storyPart.appendChild(partpovcontainer)
    }

    updateBackground(variant.background);
    updateImage(variant.image);
    updateWeather(variant.weather);
    updateMusic(variant.music);

    // the context every line shares; branch state (pov chains, message
    // containers, the node's title) carries across lines like the old loop
    const ctx = {
        state,
        node,
        nodeId,
        storyPart,
        partPace,
        effectPart,
        partpov,
        partpovcontainer,
        // pre-increment visit number: branch 0 on the first visit, matching
        // the walk assignVisiblePovs did while entering the node
        visitNumber: Math.max(0, (state.visits[nodeId] || 1) - 1),
        partmessagepov: variant.messagepov || partpov,
        messageparttitle: variant.messagetitle,
        messagetitle: null,
        messagescontainer: null,
        lastmessageobj: null,
        lastmessagepov: null,
        lastpov: null,
        lastpovcontainer: null,
    };

    await renderLineList(variant.lines || [], ctx);
    textRevealing = false;
}

// the choices on screen right now: gated by conditions and by revisit
function activeChoiceButtons() {
    return [...storyContainer.querySelectorAll(".story-choice.active:not(:disabled)")];
}

// click / Space / Enter: finish the text reveal if it is still going, else
// follow the one choice when the story is linear at this point, else follow
// an unconditional `next`
function advanceOrReveal() {
    cancelAutoAdvance();
    if (textRevealing) {
        triggerSkip();
        return;
    }
    const choices = activeChoiceButtons();
    if (choices.length === 1) {
        choices[0].click();
        return;
    }
    if (!choices.length) applyAndRender({ type: "advance" });
}

function unselectChoices() {
    const choiceButtons = document.getElementsByClassName("story-choice");
    for (const button of choiceButtons) {
        // the restart button stays live, everything else becomes a record
        if (button.classList.contains("redo")) continue;
        button.removeEventListener("click", button._clickButton);
        button.disabled = true;
        button.classList.remove("active");
        button.classList.add("unselected");
        if (button.classList.contains("selected")) {
            button.classList.remove("unselected");
        }
    }
}

function redoButton() {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "story-choice redo";
    button.textContent = "Restart story";
    button.style.backgroundColor = config.accentColour || "#0a84ff";
    button.style.opacity = 1;

    // handle the reset action
    button.addEventListener("click", resetStory);
    return button;
}

async function renderChoices(nodeContainer, state, storyIndex, node, variant, isCurrent) {
    const choicesContainer = document.createElement("div");
    choicesContainer.className = "story-choices";
    nodeContainer.appendChild(choicesContainer);

    // the choices this step's state allows
    const choices = visibleChoices(state, node, variant, state.path, storyIndex);

    // an ending, or a node with no live exit, offers a restart instead; a
    // node about to follow `next` shows nothing and continues on advance
    const isEnd = node.end || (choices.length === 0 && !liveNext(state, node));

    const buttons = [];

    // if this is an ending node, show a redo button
    if (isEnd) {
        buttons.push(redoButton());
    }
    // otherwise, show the choices
    else {
        for (let i = 0; i < choices.length; i++) {
            const choice = choices[i];
            const choiceButton = document.createElement("button");
            choiceButton.type = "button";
            choiceButton.className = "story-choice";
            choiceButton.textContent = choice.label;
            // not clickable until every choice has finished fading in
            choiceButton.disabled = true;

            // unselected past choices get the class applied
            if (!isCurrent) {
                // if the next part of the story is this past choices target, it was chosen
                if (currentState.path[storyIndex + 1] === choice.to) {
                    choiceButton.classList.add("selected");
                } else {
                    choiceButton.classList.add("unselected");
                }
            } else {
                choiceButton.classList.add("active");
            }

            // handle the choice selection
            choiceButton._clickButton = () => {
                if (isCurrent) {
                    choiceButton.classList.add("selected");
                    unselectChoices();
                    applyAndRender({ type: "choice", index: i });
                }
            }

            choiceButton.addEventListener("click", choiceButton._clickButton);
            buttons.push(choiceButton);
        }
    }

    const speed = parseFloat(config.choiceSpeed);
    for (const button of buttons) {
        choicesContainer.appendChild(button);
        keepView();
        await wait(speed);
    }

    // enable the active choices once they are all on screen; disabled buttons
    // are skipped by the keyboard, so past choices stay out of the tab order
    if (isCurrent) {
        for (const button of buttons) {
            button.disabled = false;
        }

        // a linear node can follow its only choice on its own, so a story
        // reads hands-off; any reader input cancels it first
        const delay = Number(config.autoAdvance) || 0;
        const live = activeChoiceButtons();
        if (delay > 0 && live.length === 1) {
            cancelAutoAdvance();
            autoAdvanceTimer = setTimeout(() => {
                autoAdvanceTimer = null;
                const now = activeChoiceButtons();
                if (now.length === 1) now[0].click();
            }, delay);
        }
    }
}

async function renderNode(state, storyIndex, node) {
    const variant = nodeVariant(node, state.variants[storyIndex]);

    // create the node container
    const nodeContainer = document.createElement("div");
    nodeContainer.className = "story-node";
    storyContainer.appendChild(nodeContainer);

    // create the text
    await renderText(nodeContainer, state, node, variant, state.path[storyIndex]);

    // create the choices, if they exist
    const isCurrent = storyIndex >= stepStates.length - 1;
    await renderChoices(nodeContainer, state, storyIndex, node, variant, isCurrent);

    // ensure we have scrolled enough
    keepView();
}

// draw every step from fromIndex on, each from its own snapshot
async function renderForward(fromIndex) {
    const generation = renderGeneration;
    updateBackButton();
    for (let i = fromIndex; i < stepStates.length; i++) {
        // the view was cleared underneath us, stop appending
        if (generation !== renderGeneration) return;

        const state = stepStates[i];
        const node = storyData.nodes[state.path[i]];

        // node not implemented
        if (!node) {
            const emptyNode = document.createElement("div");
            emptyNode.className = "story-part";
            emptyNode.innerHTML = "<em>Pathway not implemented yet.</em>";
            emptyNode.dataset.speed = config.textSpeed;

            storyContainer.appendChild(emptyNode);
            await fadeText(emptyNode);

            storyContainer.appendChild(redoButton());
            keepView();
            continue;
        }

        await renderNode(state, i, node);
    }
}

// run a transition, publish the new state, draw whatever it entered
async function applyAndRender(action) {
    const result = applyTransition(currentState || emptyState(), action);
    if (!result.steps.length) return;
    const from = result.steps[0].index;
    stepStates = stepStates.slice(0, from);
    for (const step of result.steps) stepStates.push(step.state);
    currentState = result.state;
    saveStateToURL(result.state);
    await renderForward(from);
}

// wipe every trace of the previous run so a re-render starts clean
function clearView() {
    renderGeneration++;
    storyHistory = [];
    skipMode = false;
    cancelAutoAdvance();
    stepStates = [];
    currentState = emptyState();
    appliedImage = null;
    sceneImage.style.opacity = 0;
    sceneImage.style.backgroundImage = "";
    for (const entry of [...pendingWaits]) entry.finish();

    storyContainer.innerHTML = "";
    document.body.style.background = config.backgroundColour || "#111";
    storyContainer.style.color = config.textColour || "#eee";
    weatherCanvas.className = "";
    effectOverlay.style.setProperty("--focus-size", "105%");
}

async function resetStory() {
    clearView();
    hideTitle();
    stopMusic();

    const result = applyTransition(emptyState(), { type: "start" });

    // the first node gets its own history entry so Back walks
    // title -> first node -> choice -> ... instead of jumping from a
    // choice straight back to the title
    stepStates = [result.state];
    currentState = result.state;
    saveStateToURL(result.state);

    return renderForward(0);
}

// the browser Back button should walk the choices back
window.addEventListener("popstate", () => {
    if (!storyData) return;
    const state = loadStateFromURL();
    clearView();
    if (!state.path.length) {
        updateBackButton();
        showTitle();
        return;
    }
    hideTitle();
    // replay from empty: same seed, same choices, so every intermediate
    // state re-derives exactly as the original run produced it
    stepStates = computeStepStates(state);
    currentState = stepStates[stepStates.length - 1] || state;
    updateBackButton();
    renderForward(0).catch(e => error(e.message));
});

// ---- persistence helpers -------------------------------------------------
// localStorage can be unavailable (private mode, file://), so every access
// goes through these rather than throwing mid-story
function readStore(key, fallback = null) {
    try {
        const raw = window.localStorage.getItem(key);
        return raw === null ? fallback : JSON.parse(raw);
    } catch {
        return fallback;
    }
}

function writeStore(key, value) {
    try {
        window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
        // a story that cannot persist its settings still has to run
    }
}

const SAVES_KEY = "vn-template.saves";
const SETTINGS_KEY = "vn-template.settings";

function motionReduced() {
    return settings.reduceMotion || reduceMotion.matches;
}

function loadSettings() {
    const stored = readStore(SETTINGS_KEY, {});
    settings.textSpeed = Number.isFinite(stored.textSpeed) ? stored.textSpeed : null;
    settings.reduceMotion = stored.reduceMotion === true;
    settings.highContrast = stored.highContrast === true;
    settings.volume = Number.isFinite(stored.volume) ? Math.min(1, Math.max(0, stored.volume)) : 0.7;
    settings.muted = stored.muted === true;
}

function applySettings() {
    if (settings.textSpeed !== null) config.textSpeed = settings.textSpeed;
    document.body.classList.toggle("high-contrast", settings.highContrast);
    for (const track of bgmTracks) track.volume = musicVolume();
}

function renderHistoryList() {
    const list = document.getElementById("history-list");
    list.textContent = "";
    if (!storyHistory.length) {
        const li = document.createElement("li");
        li.className = "history-empty";
        li.textContent = "Nothing read yet.";
        list.appendChild(li);
        return;
    }
    for (const entry of storyHistory) {
        const li = document.createElement("li");
        li.innerHTML = entry.html;
        if (entry.pov) {
            li.classList.add("has-pov");
            li.dataset.pov = entry.pov;
        }
        list.appendChild(li);
    }
}

// restore a save (or a shared link) by replaying it from empty, the same
// way popstate does
function restoreState(restored) {
    clearView();
    if (!restored.path.length) {
        updateBackButton();
        showTitle();
        return;
    }
    hideTitle();
    const url = new URL(window.location);
    url.searchParams.set("state", encodeState(restored));
    window.history.pushState(null, "", url);
    stepStates = computeStepStates(restored);
    currentState = stepStates[stepStates.length - 1] || restored;
    updateBackButton();
    renderForward(0).catch(e => error(e.message));
}

function renderSaveSlots() {
    const wrap = document.getElementById("save-slots");
    wrap.textContent = "";
    const saves = readStore(SAVES_KEY, {});

    for (let i = 1; i <= 3; i++) {
        const slot = document.createElement("div");
        slot.className = "save-slot";

        const info = document.createElement("span");
        const data = saves[i];
        info.textContent = data
            ? `Slot ${i} - ${data.path.length} step${data.path.length === 1 ? "" : "s"}`
            : `Slot ${i} - empty`;
        slot.appendChild(info);

        const saveBtn = document.createElement("button");
        saveBtn.type = "button";
        saveBtn.textContent = "Save";
        saveBtn.addEventListener("click", () => {
            if (!storyData || !currentState.path.length) return;
            writeStore(SAVES_KEY, {
                ...saves,
                [i]: {
                    ...currentState,
                    savedAt: Date.now(),
                },
            });
            renderSaveSlots();
        });
        slot.appendChild(saveBtn);

        const loadBtn = document.createElement("button");
        loadBtn.type = "button";
        loadBtn.textContent = "Load";
        loadBtn.disabled = !data;
        loadBtn.addEventListener("click", () => {
            const latest = readStore(SAVES_KEY, {})[i];
            if (!latest) return;
            closeAllPanels();
            restoreState(sanitizeState(latest));
        });
        slot.appendChild(loadBtn);

        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.textContent = "Delete";
        delBtn.disabled = !data;
        delBtn.addEventListener("click", () => {
            const latest = { ...readStore(SAVES_KEY, {}) };
            delete latest[i];
            writeStore(SAVES_KEY, latest);
            renderSaveSlots();
        });
        slot.appendChild(delBtn);

        wrap.appendChild(slot);
    }
}

function updateBackButton() {
    document.getElementById("btn-back").disabled = !currentState || currentState.path.length <= 1;
}

function closeAllPanels() {
    for (const panel of document.querySelectorAll(".panel")) panel.hidden = true;
    for (const btn of document.querySelectorAll("[aria-controls]")) btn.setAttribute("aria-expanded", "false");
}

// ---- title screen -------------------------------------------------------
const titleScreen = document.getElementById("title-screen");

function showTitle() {
    titleScreen.hidden = false;
    document.getElementById("title-start").focus();
}

function hideTitle() {
    titleScreen.hidden = true;
}

function openPanel(btnId) {
    const btn = document.getElementById(btnId);
    const panel = document.getElementById(btn.getAttribute("aria-controls"));
    closeAllPanels();
    panel.hidden = false;
    btn.setAttribute("aria-expanded", "true");
    if (panel.id === "history-panel") renderHistoryList();
    if (panel.id === "save-panel") renderSaveSlots();
}

function initControls() {
    // panels and the story column offset themselves from the live toolbar
    // height, which changes when the buttons wrap on narrow screens
    const toolbar = document.getElementById("toolbar");
    const syncToolbar = () =>
        document.documentElement.style.setProperty("--toolbar-height", `${toolbar.offsetHeight}px`);
    new ResizeObserver(syncToolbar).observe(toolbar);
    syncToolbar();

    const toggles = [
        ["btn-history", "history-panel"],
        ["btn-save", "save-panel"],
        ["btn-settings", "settings-panel"],
    ];

    for (const [btnId, panelId] of toggles) {
        const btn = document.getElementById(btnId);
        const panel = document.getElementById(panelId);
        btn.addEventListener("click", () => {
            const willOpen = panel.hidden;
            closeAllPanels();
            if (willOpen) openPanel(btnId);
        });
    }

    for (const btn of document.querySelectorAll(".panel-close")) {
        btn.addEventListener("click", closeAllPanels);
    }

    document.addEventListener("keydown", e => {
        if (e.key === "Escape") { closeAllPanels(); return; }

        // never hijack keys while a form control has focus
        if (e.target.closest("input, textarea, select")) return;

        // Space / Enter: finish the reveal, or follow the lone choice; when a
        // control itself has focus, let its native activation handle the key
        if (e.key === " " || e.key === "Enter") {
            if (e.target.closest("button, a")) return;
            e.preventDefault();
            advanceOrReveal();
            return;
        }

        // 1-9 picks that numbered choice
        if (/^[1-9]$/.test(e.key)) {
            const choices = activeChoiceButtons();
            const picked = choices[Number(e.key) - 1];
            if (picked) {
                e.preventDefault();
                picked.click();
            }
        }
    });

    // click anywhere that is not a control: finish the reveal, or follow the
    // lone choice (a branching point still needs an explicit pick)
    document.addEventListener("click", e => {
        if (e.target.closest("button, a, input, textarea, select, .panel, #toolbar, #title-screen")) return;
        advanceOrReveal();
    });

    document.getElementById("btn-back").addEventListener("click", () => window.history.back());
    document.getElementById("btn-skip").addEventListener("click", triggerSkip);
    document.getElementById("set-restart").addEventListener("click", () => {
        closeAllPanels();
        hideTitle();
        resetStory();
    });

    // title screen
    document.getElementById("title-heading").textContent = document.title;
    document.getElementById("title-start").addEventListener("click", () => {
        hideTitle();
        resetStory();
    });
    document.getElementById("title-load").addEventListener("click", () => openPanel("btn-save"));
    document.getElementById("title-settings").addEventListener("click", () => openPanel("btn-settings"));

    // settings
    const speedInput = document.getElementById("set-text-speed");
    const speedOut = document.getElementById("set-text-speed-out");
    speedInput.value = settings.textSpeed ?? config.textSpeed;
    speedOut.textContent = `${speedInput.value}ms`;
    speedInput.addEventListener("input", () => {
        settings.textSpeed = Number(speedInput.value);
        config.textSpeed = settings.textSpeed;
        speedOut.textContent = `${speedInput.value}ms`;
        writeStore(SETTINGS_KEY, settings);
    });

    const motionInput = document.getElementById("set-reduced-motion");
    motionInput.checked = settings.reduceMotion;
    motionInput.addEventListener("change", () => {
        settings.reduceMotion = motionInput.checked;
        writeStore(SETTINGS_KEY, settings);
    });

    const contrastInput = document.getElementById("set-high-contrast");
    contrastInput.checked = settings.highContrast;
    contrastInput.addEventListener("change", () => {
        settings.highContrast = contrastInput.checked;
        document.body.classList.toggle("high-contrast", settings.highContrast);
        writeStore(SETTINGS_KEY, settings);
    });

    const volumeInput = document.getElementById("set-volume");
    const volumeOut = document.getElementById("set-volume-out");
    volumeInput.value = Math.round(settings.volume * 100);
    volumeOut.textContent = `${volumeInput.value}%`;
    volumeInput.addEventListener("input", () => {
        settings.volume = Number(volumeInput.value) / 100;
        volumeOut.textContent = `${volumeInput.value}%`;
        if (!settings.muted) for (const track of bgmTracks) track.volume = settings.volume;
        writeStore(SETTINGS_KEY, settings);
    });

    const muteInput = document.getElementById("set-mute");
    muteInput.checked = settings.muted;
    muteInput.addEventListener("change", () => {
        settings.muted = muteInput.checked;
        for (const track of bgmTracks) track.volume = musicVolume();
        writeStore(SETTINGS_KEY, settings);
    });
}

const settings = { textSpeed: null, reduceMotion: false, highContrast: false, volume: 0.7, muted: false };

// Start the rendering of the story plz
async function initStory() {
    showStatus("Loading story…");
    try {
        await loadConfig();
        applyTheme();
        await loadColours();

        document.body.style.background = config.backgroundColour || "#111";
        storyContainer.style.color = config.textColour || "#eee";

        // layout settings live in css, but their values come from the config
        if (config.maxTextWidth) {
            document.documentElement.style.setProperty("--max-text-width", `${config.maxTextWidth}px`);
        }
        if (config.scenePadding) {
            document.documentElement.style.setProperty("--scene-padding", config.scenePadding);
        }

        const res = await fetch("story.json");
        if (!res.ok) {
            throw new Error(`story.json returned ${res.status} - run python3 src/generate_story.py first`);
        }
        storyData = await res.json();
        if (storyData.version !== 2 || !storyData.nodes) {
            throw new Error("story.json is not version 2 - run python3 src/generate_story.py first");
        }

        const state = loadStateFromURL();

        loadSettings();
        applySettings();
        initControls();

        hideStatus();
        if (state.path.length) {
            // a shared link or a reload: replay it so every step's state is
            // rebuilt exactly, then draw the whole path
            stepStates = computeStepStates(state);
            currentState = stepStates[stepStates.length - 1] || state;
            await renderForward(0);
        } else {
            currentState = emptyState();
            // nothing in the url yet: the reader picks when to begin
            showTitle();
        }
        updateBackButton();
    } catch (e) {
        console.error(e);
        showStatus(`Could not start the story: ${e.message}`, () => window.location.reload());
    }
}

initStory();
