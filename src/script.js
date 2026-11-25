const storyContainer = document.getElementById("story-container");
const weatherCanvas = document.getElementById("weather-canvas");
const effectOverlay = document.getElementById("effect-overlay");

let config;
let colours;
let storyData;
let povColours = {};
let lastNode = -1;

// Regexes

let COLOUR_PATTERN;
let BACKGROUND_PATTERN;

const PACE_PATTERN = /\/(slowest|slower|slow|fastest|faster|fast|pace \d+\s?(ms|s))/ig;
const PAUSE_PATTERN = /^\/pause \d+\s?(ms|s)$/ig;

const EFFECT_PATTERN = /\/(bounce|blink|glow|wave)/ig;

const POV_PATTERN = /\/pov \w+/ig;

const MESSAGE_UNSENT_PATTERN = /\/message\-unsent \w+/ig;
const MESSAGE_PATTERN = /\/message (\w+)/ig;
const MESSAGE_TITLE_PATTERN = /^\/message\-title [^/]+$/ig;

const BACKGROUND_EFFECT_PATTERN = /^\/(?:(focus) (\d+(?:\.\d+)?%|reset)|(effect reset))$/ig;

const WEATHER_PATTERN = /^\/(rain|snow|fog|fireflies|sunny|clear|none)$/ig;

const SFX_PATTERN = /^\/sfx ([\w.-]+)$/ig;

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


async function loadColours() {
    const text = await fetch("named_colours").then(r => r.text());
    colours = text.toLowerCase().split(/\r?\n/).filter(Boolean);
    COLOUR_PATTERN = new RegExp(`\/(${colours.join('|')}|reset|colour #(?:[0-9a-f]{3}){1,2})`, "gi");
    BACKGROUND_PATTERN = new RegExp(`^\/background (${colours.join('|')}|reset|#(?:[0-9a-f]{3}){1,2})$`, "gi");
}

// URL to state and back
function emptyState() {
    return { path: [], variants: [], povColours: {}, flags: [], vars: {} };
}

// a shared link can be stale or hand edited, never trust its shape
function sanitizeState(state) {
    if (!state || typeof state !== "object" || Array.isArray(state)) return emptyState();

    const path = [];
    if (Array.isArray(state.path)) {
        for (const node of state.path) {
            if (typeof node !== "string") break;
            path.push(node);
        }
    }

    const variants = Array.isArray(state.variants)
        ? state.variants.slice(0, path.length).map(v => Number.isInteger(v) && v >= 0 ? v : null)
        : [];

    const povColours = {};
    if (state.povColours && typeof state.povColours === "object" && !Array.isArray(state.povColours)) {
        for (const [key, value] of Object.entries(state.povColours)) {
            if (typeof key === "string" && typeof value === "string") povColours[key] = value;
        }
    }

    const flags = Array.isArray(state.flags)
        ? state.flags.filter(flag => typeof flag === "string")
        : [];

    const vars = {};
    if (state.vars && typeof state.vars === "object" && !Array.isArray(state.vars)) {
        for (const [key, value] of Object.entries(state.vars)) {
            if (typeof key === "string" && typeof value === "number" && isFinite(value)) {
                vars[key] = value;
            }
        }
    }

    return { path, variants, povColours, flags, vars };
}

function loadStateFromURL() {
    const params = new URLSearchParams(window.location.search);
    const encodedState = params.get("state");
    if (!encodedState) return emptyState();
    try {
        return sanitizeState(JSON.parse(atob(encodedState)));
    } catch {
        return emptyState();
    }
}

function statePayload(path, variants) {
    return JSON.stringify({ path, variants, povColours, flags: [...currentFlags], vars: { ...currentVars } });
}

function saveStateToURL(path, variants) {
    const url = new URL(window.location);
    url.searchParams.set("state", btoa(statePayload(path, variants)));
    // push, not replace: the reader expects the browser Back button to undo
    // the choice they just made
    window.history.pushState(null, "", url);
    updateBackButton();
}

// flags raised mid-node still have to survive a reload, so the current entry
// is rewritten once they are known
function syncStateToURL() {
    if (!currentPath.length) return;
    const url = new URL(window.location);
    if (!url.searchParams.has("state")) return;
    url.searchParams.set("state", btoa(statePayload(currentPath, currentVariants)));
    window.history.replaceState(null, "", url);
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

// flags raised by the nodes visited so far; every state snapshot carries
// them so Back and saves restore the same set
let currentFlags = new Set();

// numeric variables raised by nodes visited so far; same deal, carried in
// every snapshot so Back and saves restore them
let currentVars = {};

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

function extractRegex(line, regex = COLOUR_PATTERN) {
    const match = line.match(regex);
    if (match) {
        const found = match[0].startsWith("/") ? match[0].slice(1) : match[0];
        return [found, line.replace(regex, "")];
    }
    return [null, line];
}

function extractRegexArg(line, regex = COLOUR_PATTERN) {
    const match = line.match(regex);
    if (match) {
        const found = match[0].split(" ");
        const args = found.slice(1).join(" ");
        return [args, line.replace(regex, ""), found[0].replace("/", "")];
    }
    return [null, line];
}

function extractMultipleRegex(line, regex = EFFECT_PATTERN) {
    const match = line.match(regex);
    if (match) {
        let matches = [];
        for (const m of match) { matches.push(m.replace("\/", "")); }
        return [matches, line.replace(regex, "")];
    }
    return [null, line];
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

// find the canonically cased key for a pov, so "You" and "you" share a colour
function povKey(pov) {
    if (!pov || !config.povCaseInsensitive) { return pov; }
    const match = Object.keys(povColours).find(key => key.toLowerCase() === pov.toLowerCase());
    return match || pov;
}

function parsePOVColour(pov, partpov = null) {
    if (!pov) { return null; }
    const key = povKey(pov);
    if (povColours[key]) { return povColours[key]; }

    const used = Object.values(povColours);
    let pool = colours.filter(col => !used.includes(col));
    if (!pool.length) { pool = colours; }

    const partkey = partpov ? povKey(partpov) : null;
    if (partkey && povColours[partkey]) {
        const contrasting = pool.filter(col => contrast(col, povColours[partkey]) >= 10);
        if (contrasting.length) { pool = contrasting; }
    }

    const selected = pool[Math.floor(Math.random() * pool.length)];
    povColours[key] = selected;
    return selected;
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


function createPOVContainer(pov, partpov = null) {
    const povContainer = document.createElement("div");
    const povName = document.createElement("div");
    const colour = parsePOVColour(pov, partpov);

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

function addNewLine(part, line, pov, lastpov, lastpovcontainer, partpov) {
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
            const newpovcontainer = createPOVContainer(pov, !isPart ? partpov : null);
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

function formatMessage(storypart, messagecontainer, messageObj, lastmsgObj, pov, lastpov, partpov, unsent, messagetitle) {
    const povcolour = parsePOVColour(pov, partpov);
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
        case "focus":
            const percent = parseFloat(value.replace("reset", "100").replace("%", ""));
            effectOverlay.style.setProperty("--focus-size", `${percent}%`);
            break;
        default:
            // reset all effects
            effectOverlay.style.setProperty("--focus-size", "105%");
            updateBackground("reset");
            break;
    }
}


async function renderText(nodeContainer, node, variantIdx) {
    const storyPart = document.createElement("div");
    storyPart.className = "story-part";

    nodeContainer.appendChild(storyPart);

    const variant = node.variants[variantIdx];
    textRevealing = true;

    // extract the node colour choice
    const partColour = variant.colour;
    storyPart.style.color = partColour;

    // extract the speed for this part
    const partPace = parsePaceMultiplier(variant.pace);

    // extract any effect classes
    const effectPart = variant.effect ? variant.effect.split() : [];

    const partpov = variant.pov;
    let partpovcontainer;
    if (partpov) {
        partpovcontainer = createPOVContainer(partpov);
        storyPart.appendChild(partpovcontainer)
    }
    let lastpov;
    let lastpovcontainer;

    // messaging pov
    let partmessagepov = variant.messagepov || partpov;
    let lastmessageobj;
    let lastmessagepov;
    let messagescontainer;

    // messaging title
    const messageparttitle = variant.messagetitle;
    let messagetitle;

    // background effects
    updateBackground(variant.background);
    updateImage(variant.image);
    updateWeather(variant.weather);
    updateMusic(variant.music);

    // print the lines
    const lines = variant.text.split("\n").filter(elem => elem.trim());
    // conditional blocks: /if <cond> ... [/else] ... /endif; a line renders
    // only when every enclosing block is showing
    const condStack = [];
    const showing = () => condStack.every(entry => entry.show);
    for (const line of lines) {
        const stripped = line.trim();

        const ifMatch = stripped.match(/^\/if\s+(.+)$/i);
        if (ifMatch) {
            condStack.push({ show: evalCondition(ifMatch[1]), orElse: false });
            continue;
        }
        if (/^\/else$/i.test(stripped)) {
            const entry = condStack[condStack.length - 1];
            if (entry) entry.show = !entry.show;
            continue;
        }
        if (/^\/endif$/i.test(stripped)) {
            condStack.pop();
            continue;
        }

        // inside a block whose condition failed: skip the line entirely, so it
        // never renders, never enters history, and never fires a command
        if (!showing()) continue;

        // single line commands that should exit early
        const foundtitle = extractRegexArg(line, MESSAGE_TITLE_PATTERN)[0];
        if (foundtitle) {
            messagetitle = foundtitle.replace("message-title", "").trim();
            continue;
        }

        const foundpause = extractRegexArg(line, PAUSE_PATTERN)[0];
        if (foundpause) {
            await wait(toMillis(foundpause));
            continue;
        }

        const [foundbgvalue, _, foundbgeffect] = extractRegexArg(line, BACKGROUND_EFFECT_PATTERN);
        if (foundbgeffect) {
            updateEffect(foundbgeffect, foundbgvalue);
            continue
        }

        const foundbackground = extractRegexArg(line, BACKGROUND_PATTERN)[0];
        if (foundbackground) {
            updateBackground(foundbackground);
            continue
        }

        const foundweather = extractRegex(line, WEATHER_PATTERN)[0];
        if (foundweather) {
            updateWeather(foundweather);
            continue
        }

        const foundsfx = extractRegexArg(line, SFX_PATTERN)[0];
        if (foundsfx) {
            playSfx(foundsfx);
            continue
        }

        // commands that still output text
        const storyLine = document.createElement("div");
        storyLine.className = "story-line";

        const [col, colourless_line] = extractRegex(line, COLOUR_PATTERN);
        if (col) { storyLine.style.color = col.replace("colour", "").replace("reset", config.textColour).trim(); }

        const [pace, paceless_line] = extractRegex(colourless_line, PACE_PATTERN);

        const [effects, effectless_text] = extractMultipleRegex(paceless_line, EFFECT_PATTERN);
        if (effects) { storyLine.classList.add(...effects); };
        if (effectPart) { storyLine.classList.add(...effectPart); };

        // register povs if needed
        const [pov, povlesstext] = extractRegexArg(effectless_text, POV_PATTERN);

        // determine any messages
        const [unsentmessagepov, unsentlesstext] = extractRegexArg(povlesstext, MESSAGE_UNSENT_PATTERN);
        const [messagepov, messagelesstext] = extractRegexArg(unsentlesstext, MESSAGE_PATTERN);

        // substitute {name} references to numeric variables so a score or
        // health value can appear inline; unknown names are left alone
        const substituted = messagelesstext.replace(/\{(\w+)\}/g, (m, name) =>
            name in currentVars ? String(currentVars[name]) : m
        );

        // parse markdown to html; marked allows raw html through, so it goes
        // into innerHTML only after DOMPurify has stripped anything active
        storyLine.innerHTML = DOMPurify.sanitize(marked.parse(substituted));

        storyHistory.push({ html: storyLine.innerHTML, pov: pov || partpov });

        // render as a message or not
        const foundmessagepov = unsentmessagepov || messagepov;
        if (foundmessagepov) {
            if (!partmessagepov) { partmessagepov = foundmessagepov; }
            [messagescontainer, lastmessageobj, lastmessagepov] = formatMessage(storyPart, messagescontainer, storyLine, lastmessageobj, foundmessagepov, lastmessagepov, partmessagepov, unsentmessagepov, messagetitle || messageparttitle);
            lastpovcontainer = null;
            lastpov = null;
        } else {
            messagescontainer = null;
            lastmessageobj = null;
            lastmessagepov = null;
            messagetitle = null;
            lastpovcontainer = addNewLine(partpovcontainer || storyPart, storyLine, pov || partpov, lastpov, lastpovcontainer, partpov);
            lastpov = pov || variant.pov;
        }

        // ensure we wait the right amount of time between lines of text
        const speed = parsePaceMultiplier(pace) * partPace * config.textSpeed;
        storyLine.dataset.speed = speed;
        await fadeText(storyLine);
    }
    textRevealing = false;
}

// the choices the reader can pick right now: the current node's, once they
// have finished fading in (past choices stay disabled)
function activeChoiceButtons() {
    return [...storyContainer.querySelectorAll(".story-choice.active:not(:disabled)")];
}

// click / Space / Enter: finish the text reveal if it is still going, else
// follow the one choice when the story is linear at this point
function advanceOrReveal() {
    cancelAutoAdvance();
    if (textRevealing) {
        triggerSkip();
        return;
    }
    const choices = activeChoiceButtons();
    if (choices.length === 1) choices[0].click();
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

// a story.json written before flags existed has a flat label -> target map
function normaliseChoices(choices) {
    if (!choices) return [];
    if (Array.isArray(choices)) return choices;
    return Object.entries(choices).map(([label, to]) => ({ label, to }));
}

function visitable(path, choices) {
    return normaliseChoices(choices).filter(choice => {
        // gated on a condition the reader has not satisfied yet
        if (choice.if && !choice.if.every(evalCondition)) return false;

        const node = storyData[choice.to];
        if (!node) return true; // unimplemented, sure, let it show
        const alreadyVisited = path.slice(0, lastNode + 2).includes(choice.to);
        return !alreadyVisited || node.revisit;
    });
}

// a condition is a (possibly negated) flag name, or a numeric comparison
// against a variable: score >= 10
function evalCondition(condition) {
    let cond = String(condition).trim();
    let negate = false;
    if (/^not\s+/i.test(cond)) {
        negate = true;
        cond = cond.replace(/^not\s+/i, "").trim();
    }

    let result;
    const cmp = cond.match(/^(.+?)\s*(>=|<=|==|!=|>|<)\s*(-?\d+(?:\.\d+)?)$/);
    if (cmp) {
        const current = currentVars[cmp[1].trim()] ?? 0;
        const target = parseFloat(cmp[3]);
        switch (cmp[2]) {
            case ">=": result = current >= target; break;
            case "<=": result = current <= target; break;
            case ">": result = current > target; break;
            case "<": result = current < target; break;
            case "==": result = current === target; break;
            case "!=": result = current !== target; break;
        }
    } else {
        result = currentFlags.has(cond);
    }

    return negate ? !result : result;
}


async function renderChoices(nodeContainer, path, variants, storyIndex, node, variantIdx) {
    const choicesContainer = document.createElement("div");
    choicesContainer.className = "story-choices";
    nodeContainer.appendChild(choicesContainer);

    // fetch the variants so we can find the choices allowed
    const variant = node.variants[variantIdx];

    // fetch the choices for this node
    const choices = variant.choices ? visitable(path, variant.choices) : [];

    // determine if these choices have already been made
    const isCurrent = storyIndex >= path.length - 1;

    // and if there are further choices to be made
    const isEnd = node.end || choices.length === 0;

    const buttons = [];

    // if this is an ending node, show a redo button
    if (isEnd) {
        buttons.push(redoButton());
    }
    // otherwise, show the choices
    else {
        for (const choice of choices) {
            const choiceButton = document.createElement("button");
            choiceButton.type = "button";
            choiceButton.className = "story-choice";
            choiceButton.textContent = choice.label;
            // not clickable until every choice has finished fading in
            choiceButton.disabled = true;

            // unselected past choices get the class applied
            if (!isCurrent) {
                // if the next part of the story is this past choices target, it was chosen
                if (path[storyIndex + 1] === choice.to) {
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
                    path.push(choice.to);
                    variants.push(variantIdx);
                    choiceButton.classList.add("selected");
                    saveStateToURL(path, variants);
                    unselectChoices();
                    renderPath(path, variants, storyIndex + 1);
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

async function renderNode(path, variants, storyIndex, node, variantIdx) {
    // a skip only lasts for the node it was pressed during
    skipMode = false;
    // any pending auto-follow belongs to the node we are leaving
    cancelAutoAdvance();

    // flags this node raises become live as soon as it is on screen, ahead
    // of its own choices being filtered
    const variant = node.variants[variantIdx];
    if (variant && variant.sets && variant.sets.length) {
        const raised = variant.sets.filter(flag => !currentFlags.has(flag));
        for (const flag of raised) currentFlags.add(flag);
        if (raised.length) syncStateToURL();
    }

    // numeric variables are applied the same way; a plain number sets the
    // value, a "+n"/"-n" string adjusts it
    if (variant && variant.vars && Object.keys(variant.vars).length) {
        let changed = false;
        for (const [name, value] of Object.entries(variant.vars)) {
            if (typeof value === "number") {
                if (currentVars[name] !== value) changed = true;
                currentVars[name] = value;
            } else {
                const delta = parseFloat(value);
                currentVars[name] = (currentVars[name] ?? 0) + delta;
                changed = true;
            }
        }
        if (changed) syncStateToURL();
    }

    // create the node container
    const nodeContainer = document.createElement("div");
    nodeContainer.className = "story-node";
    storyContainer.appendChild(nodeContainer);

    // create the text
    await renderText(nodeContainer, node, variantIdx);

    // create the choices, if they exist
    // because choices will progress the story, we need to pass the path and variants trackers
    await renderChoices(nodeContainer, path, variants, storyIndex, node, variantIdx);

    // ensure we have scrolled enough
    keepView();
}

function chooseVariant(node, index = null) {
    // use the defined variant, or select one at random
    if (Number.isInteger(index) && index >= 0 && index < node.variants.length) {
        return index;
    }
    return Math.floor(Math.random() * node.variants.length);
}

// Render the story
async function renderPath(path, variants, startIndex = null) {
    const generation = renderGeneration;
    currentPath = path;
    currentVariants = variants;
    updateBackButton();
    const fromIndex = startIndex ?? lastNode + 1;
    for (let i = fromIndex; i < path.length; i++) {
        // the view was cleared underneath us, stop appending
        if (generation !== renderGeneration) return;

        const nodeName = path[i];
        const node = storyData[nodeName];

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

        // fetch the current variant, and then render.
        const variantIdx = chooseVariant(node, variants[i]);
        await renderNode(path, variants, i, node, variantIdx);
        lastNode = i;
    }
}

function updatePOVColours(povState) {
    if (!povState) { return }
    for (const [key, value] of Object.entries(povState)) {
        if (!povColours[key]) {
            povColours[key] = value;
        }
    }
}

// wipe every trace of the previous run so a re-render starts clean
function clearView() {
    renderGeneration++;
    lastNode = -1;
    storyHistory = [];
    skipMode = false;
    cancelAutoAdvance();
    currentFlags = new Set();
    currentVars = {};
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

function pickStartNode() {
    const startNodes = Object.entries(storyData).filter(([, v]) => v.start).map(([k]) => k);
    if (!startNodes.length) {
        error("No starting story nodes defined");
    }
    return startNodes[Math.floor(Math.random() * startNodes.length)];
}

function resetStory() {
    clearView();
    hideTitle();
    stopMusic();

    // the first node gets its own history entry so Back walks
    // title -> first node -> choice -> ... instead of jumping from a
    // choice straight back to the title
    const path = [pickStartNode()];
    currentPath = path;
    currentVariants = [];
    saveStateToURL(path, []);

    return renderPath(path, []);
}

// the browser Back button should walk the choices back
window.addEventListener("popstate", () => {
    if (!storyData) return;
    const state = loadStateFromURL();
    clearView();
    currentFlags = new Set(state.flags);
    currentVars = { ...state.vars };
    updatePOVColours(state.povColours);
    updateBackButton();
    if (!state.path.length) {
        showTitle();
        return;
    }
    hideTitle();
    renderPath(state.path, state.variants).catch(e => error(e.message));
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

// the arrays renderPath is walking, so the save panel can snapshot them
let currentPath = [];
let currentVariants = [];

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
            if (!storyData) return;
            writeStore(SAVES_KEY, {
                ...saves,
                [i]: {
                    path: [...currentPath],
                    variants: [...currentVariants],
                    povColours: { ...povColours },
                    flags: [...currentFlags],
                    vars: { ...currentVars },
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
            hideTitle();
            clearView();
            currentFlags = new Set(latest.flags || []);
            currentVars = { ...(latest.vars || {}) };
            updatePOVColours(latest.povColours);
            const url = new URL(window.location);
            url.searchParams.set("state", btoa(JSON.stringify(latest)));
            window.history.pushState(null, "", url);
            updateBackButton();
            renderPath([...latest.path], [...latest.variants]).catch(e => error(e.message));
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
    document.getElementById("btn-back").disabled = currentPath.length <= 1;
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
        updatePOVColours(config.povColours);

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

        const state = loadStateFromURL();
        const path = state["path"];

        updatePOVColours(state["povColours"]);
        currentFlags = new Set(state.flags);
        currentVars = { ...state.vars };

        loadSettings();
        applySettings();
        initControls();

        hideStatus();
        if (path.length) {
            await renderPath(path, state["variants"]);
        } else {
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
