// effects that build a gradient or path per particle per frame were the main
// source of frame drops, so repeated shapes are rasterised once and cached
const spriteCache = new Map();
function sprite(key, size, paint) {
	let s = spriteCache.get(key);
	if (s) return s;
	s = document.createElement("canvas");
	s.width = size;
	s.height = size;
	paint(s.getContext("2d"), size);
	spriteCache.set(key, s);
	return s;
}

// a tight bright core inside a wide dim halo, matching the two-pass original
function fireflySprite(size = 64) {
	return sprite(`firefly:${size}`, size, (ctx, n) => {
		const c = n / 2;
		const halo = ctx.createRadialGradient(c, c, 0, c, c, c);
		halo.addColorStop(0, "rgba(255,235,150,0.55)");
		halo.addColorStop(0.35, "rgba(255,235,150,0.16)");
		halo.addColorStop(1, "rgba(255,235,150,0)");
		ctx.fillStyle = halo;
		ctx.fillRect(0, 0, n, n);

		const core = ctx.createRadialGradient(c, c, 0, c, c, n * 0.14);
		core.addColorStop(0, "rgba(255,255,150,0.95)");
		core.addColorStop(1, "rgba(255,255,150,0)");
		ctx.fillStyle = core;
		ctx.fillRect(0, 0, n, n);
	});
}

class WeatherSystem {
	constructor(canvasId, opts = {}) {
		this.canvas = document.getElementById(canvasId);
		if (!this.canvas) {
			console.error("Weather canvas not found:", canvasId);
			return;
		}
		this.ctx = this.canvas.getContext("2d", { alpha: true });
		this.width = 0;
		this.height = 0;
		this.running = false;
		this.resize();

		this.currentEffect = null; // effect object
		this.nextEffect = null;    // effect object for transition in
		this.transitionAlpha = 0;  // 0..1 (0 = current only, 1 = next only)
		this.transitioning = false;
		this.transitionDuration = opts.transitionDuration ?? 1500; // ms
		this.clearFadeDuration = opts.clearFadeDuration ?? 600; // ms to fade to clear
		this.lastTS = performance.now();

		this.globalAlpha = 1.0;

		window.addEventListener("resize", () => this.resize());
		document.addEventListener("visibilitychange", () => {
			if (!document.hidden) this.kick();
		});

		const observer = new MutationObserver(() => this.onClassChange());
		observer.observe(this.canvas, { attributes: true, attributeFilter: ["class"] });

		this.kick();
	}

	// nothing visible to draw means the loop can stop entirely instead of
	// clearing a full screen canvas 60 times a second forever
	idle() {
		return !this.transitioning && !this.currentEffect && !this.nextEffect;
	}

	// rAF is already throttled by the browser for hidden tabs, so there is no
	// reason to gate on visibility here; all this needs to do is ensure a loop
	// is queued whenever there is something to draw
	kick() {
		if (this.running) return;
		this.running = true;
		this.lastTS = performance.now();
		requestAnimationFrame(ts => this.update(ts));
	}

	resize() {
		const dpr = Math.max(1, window.devicePixelRatio || 1);
		this.canvas.width = Math.round(window.innerWidth * dpr);
		this.canvas.height = Math.round(window.innerHeight * dpr);
		this.canvas.style.width = `${window.innerWidth}px`;
		this.canvas.style.height = `${window.innerHeight}px`;
		this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
		this.width = window.innerWidth;
		this.height = window.innerHeight;

		if (this.currentEffect && this.currentEffect.onResize) this.currentEffect.onResize(this.width, this.height);
		if (this.nextEffect && this.nextEffect.onResize) this.nextEffect.onResize(this.width, this.height);
	}

	onClassChange() {
		const cls = (this.canvas.className || "").trim();
		const match = cls.match(/weather-([a-z-]+)/);
		const newType = match ? match[1] : "clear";
		this.setWeather(newType);
	}

	setWeather(type) {
		type = (type || "clear").toLowerCase();
		if (type === "none" || type === "clear") {
			// transition to empty
			if (!this.currentEffect) return;
			this.nextEffect = null;
			this.startTransition(this.clearFadeDuration);
			this.kick();
			return;
		}

		if (this.currentEffect && this.currentEffect.type === type && !this.transitioning) return;

		if (this.nextEffect && this.nextEffect.type === type) return;

		this.transitionAlpha = 0;
		this.nextEffect = WeatherEffectFactory.create(type, this.width, this.height);
		if (!this.nextEffect) {
			console.warn("Unknown weather type:", type);
			return;
		}
		if (this.nextEffect.onStart) this.nextEffect.onStart();

		this.startTransition(this.transitionDuration);
		this.kick();
	}

	startTransition(duration) {
		this.transitioning = true;
		this.transitionDuration = Math.max(1, duration || this.transitionDuration);
		this.transitionStartTS = performance.now();
		this.transitionAlpha = 0;
	}

	update(ts) {
		const dt = Math.min(100, ts - this.lastTS);
		this.lastTS = ts;

		if (this.transitioning) {
			const elapsed = ts - this.transitionStartTS;
			const t = Math.min(1, elapsed / this.transitionDuration);
			this.transitionAlpha = t;
			if (t >= 1) {
				if (this.currentEffect && this.currentEffect.onStop) this.currentEffect.onStop();
				this.currentEffect = this.nextEffect;
				this.nextEffect = null;
				this.transitioning = false;
				this.transitionAlpha = 0;
			}
		}

		if (this.currentEffect && this.currentEffect.update) this.currentEffect.update(dt);
		if (this.nextEffect && this.nextEffect.update) this.nextEffect.update(dt);

		this.draw();

		if (this.idle()) {
			this.running = false;
			return;
		}
		requestAnimationFrame(s => this.update(s));
	}

	clearCanvas() {
		this.ctx.clearRect(0, 0, this.width, this.height);
	}

	draw() {
		const ctx = this.ctx;
		this.clearCanvas();

		if (this.transitioning) {
			const outA = 1 - this.transitionAlpha;
			const inA = this.transitionAlpha;
			if (this.currentEffect && this.currentEffect.draw && outA > 0) {
				ctx.save();
				ctx.globalAlpha = this.globalAlpha * outA;
				this.currentEffect.draw(ctx, outA);
				ctx.restore();
			}
			if (this.nextEffect && this.nextEffect.draw && inA > 0) {
				ctx.save();
				ctx.globalAlpha = this.globalAlpha * inA;
				this.nextEffect.draw(ctx, inA);
				ctx.restore();
			}
		} else {
			if (this.currentEffect && this.currentEffect.draw) {
				ctx.save();
				ctx.globalAlpha = this.globalAlpha;
				this.currentEffect.draw(ctx, 1);
				ctx.restore();
			}
		}
	}
}


const WeatherEffectFactory = {
	create(type, w, h) {
		switch (type) {
			case "rain": return new EffectRain(w, h);
			case "snow": return new EffectSnow(w, h);
			case "fog": return new EffectFog(w, h);
			case "fireflies": return new EffectFireflies(w, h);
			case "sunny": return new EffectSunny(w, h);
			default: return null;
		}
	}
};


function rnd(min = 0, max = 1) { return min + Math.random() * (max - min); }
function irnd(min, max) { return Math.floor(rnd(min, max + 1)); }


class BaseEffect {
	constructor(w, h) {
		this.w = w; this.h = h; this.type = "base";
	}
	onStart() { }
	onStop() { }
	onResize(w, h) { this.w = w; this.h = h; }
	update(dt) { }
	draw(ctx, alpha = 1) { }
}


class EffectRain extends BaseEffect {
	constructor(w, h, d = 1, v = 1) {
		super(w, h);
		this.type = "rain";
		this.particles = [];
		this.density = d * Math.round((w * h) / 4000);
		this.velocity = v;
		this.angle = 0;
		this.spawn();
	}
	spawn() {
		this.particles.length = 0;
		for (let i = 0; i < this.density; i++) {
			this.particles.push({
				x: Math.random() * this.w,
				y: Math.random() * this.h,
				length: rnd(8, 22),
				speed: this.velocity * rnd(0.4, 1.1),
			});
		}
	}
	onResize(w, h, d = 1) {
		super.onResize(w, h); this.density = d * Math.round((w * h) / 4000); this.spawn();
	}
	update(dt) {
		this.angle += rnd(-0.001, 0.001);
		for (const p of this.particles) {
			p.y += p.speed * dt;
			p.x += Math.sin(this.angle) * 2 * (dt / 16.67);
			if (p.y > this.h) { p.y = -p.length; p.x = Math.random() * this.w; }
		}
	}
	draw(ctx) {
		// one path and one stroke for every drop instead of one per drop
		const drift = Math.sin(this.angle);
		ctx.strokeStyle = "rgba(255,255,255,0.3)";
		ctx.lineWidth = 1;
		ctx.beginPath();
		for (const p of this.particles) {
			ctx.moveTo(p.x, p.y);
			ctx.lineTo(p.x + drift * p.length, p.y + p.length);
		}
		ctx.stroke();
	}
}


class EffectSnow extends BaseEffect {
	constructor(w, h) {
		super(w, h);
		this.type = "snow";
		this.particles = [];
		this.count = Math.max(60, Math.round((w * h) / 9000));
		this.spawn();
	}
	spawn() {
		this.particles = [];
		for (let i = 0; i < this.count; i++) {
			this.particles.push({
				x: Math.random() * this.w,
				y: Math.random() * this.h,
				r: rnd(0.8, 3.2),
				vy: rnd(20, 80) / 1000,
				vx: rnd(-0.1, 0.1),
				sway: rnd(0.001, 0.006),
				angle: Math.random() * Math.PI * 2
			});
		}
	}
	onResize(w, h) {
		super.onResize(w, h); this.count = Math.max(60, Math.round((w * h) / 9000)); this.spawn();
	}
	update(dt) {
		for (const p of this.particles) {
			p.angle += p.sway * dt;
			p.x += p.vx * dt + Math.sin(p.angle) * 0.02 * dt;
			p.y += p.vy * dt;
			if (p.y > this.h + 10) { p.y = -10; p.x = Math.random() * this.w; }
		}
	}
	draw(ctx) {
		// filling the circle directly is cheaper than blitting a pre-rendered
		// sprite once the sprite has to be resampled down to a few pixels
		ctx.fillStyle = "rgba(240,240,255,0.9)";
		for (const p of this.particles) {
			ctx.beginPath();
			ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
			ctx.fill();
		}
	}
}


class EffectFog extends BaseEffect {
	constructor(w, h) {
		super(w, h);
		this.type = "fog";
		this.layers = [];
		this.count = Math.max(6, Math.round((w * h) / 120000));
		this.spawn();
	}
	spawn() {
		this.layers = [];
		for (let i = 0; i < this.count; i++) {
			this.layers.push({
				x: Math.random() * this.w,
				y: Math.random() * this.h,
				r: rnd(Math.min(this.w, this.h) * 0.15, Math.min(this.w, this.h) * 0.4),
				vx: rnd(-0.02, 0.02),
				vy: rnd(-0.01, 0.01),
				opacity: rnd(0.03, 0.12)
			});
		}
	}
	onResize(w, h) {
		super.onResize(w, h); this.count = Math.max(6, Math.round((w * h) / 120000)); this.spawn();
	}
	update(dt) {
		for (const l of this.layers) {
			l.x += l.vx * dt; l.y += l.vy * dt;
			if (l.x < -l.r) l.x = this.w + l.r;
			if (l.x > this.w + l.r) l.x = -l.r;
			if (l.y < -l.r) l.y = this.h + l.r;
			if (l.y > this.h + l.r) l.y = -l.r;
		}
	}
	draw(ctx) {
		// a gradient filled directly beats blitting a small sprite, which has
		// to be resampled up to several hundred pixels per layer
		for (const l of this.layers) {
			const g = ctx.createRadialGradient(l.x, l.y, 0, l.x, l.y, l.r);
			g.addColorStop(0, `rgba(255,255,255,${l.opacity})`);
			g.addColorStop(1, "rgba(255,255,255,0)");
			ctx.fillStyle = g;
			ctx.beginPath();
			ctx.arc(l.x, l.y, l.r, 0, Math.PI * 2);
			ctx.fill();
		}
	}
}


class EffectFireflies extends BaseEffect {
	constructor(w, h) {
		super(w, h);
		this.type = "fireflies";
		this.particles = [];
		this.count = Math.max(40, Math.round((w * h) / 12000));
		this.glow = fireflySprite();
		this.spawn();
	}
	spawn() {
		this.particles = [];
		for (let i = 0; i < this.count; i++) {
			this.particles.push({
				x: Math.random() * this.w,
				y: Math.random() * this.h,
				radius: rnd(1.4, 2.2),
				speed: rnd(0.4, 1.0),
				phase: Math.random() * Math.PI * 2,
				angle: rnd(0, Math.PI * 2)
			});
		}
	}
	onResize(w, h) {
		super.onResize(w, h); this.count = Math.max(40, Math.round((w * h) / 12000)); this.spawn();
	}
	update(dt) {
		for (const p of this.particles) {
			p.phase += dt / (30 * 16.67);
			p.angle += rnd(-0.1, 0.1);
			p.x += Math.cos(p.angle) * p.speed * (dt / 16.67);
			p.y += Math.sin(p.angle) * p.speed * (dt / 16.67);
			if (p.x < 0) p.x = this.w;
			if (p.x > this.w) p.x = 0;
			if (p.y < 0) p.y = this.h;
			if (p.y > this.h) p.y = 0;
		}
	}
	draw(ctx) {
		const glow = this.glow;
		for (const p of this.particles) {
			const flicker = Math.pow(Math.sin(p.phase), 2);
			ctx.globalAlpha *= 0.25 + 0.75 * flicker;
			const d = (p.radius + 6) * 4;
			ctx.drawImage(glow, p.x - d / 2, p.y - d / 2, d, d);
			ctx.globalAlpha /= 0.25 + 0.75 * flicker;
		}
	}
}


class EffectSunny extends BaseEffect {
	constructor(w, h) {
		super(w, h);
		this.type = "sunny";
		this.pulse = 0;
		this.baked = null;
		this.place();
		this.bake();
	}
	place() {
		this.position = { x: 0.85 * this.w, y: -0.1 * this.h };
	}
	// the bloom only changes alpha, so the gradient is rasterised once at half
	// resolution and blitted rather than recomputed over the full screen
	bake() {
		const w = Math.max(1, Math.round(this.w / 2));
		const h = Math.max(1, Math.round(this.h / 2));
		const x = this.position.x / 2;
		const y = this.position.y / 2;
		const radius = Math.max(w, h) * 0.9;

		const layer = document.createElement("canvas");
		layer.width = w;
		layer.height = h;
		const ctx = layer.getContext("2d");

		const g = ctx.createRadialGradient(x, y, 0, x, y, radius);
		g.addColorStop(0, "rgba(255,245,200,0.25)");
		g.addColorStop(0.25, "rgba(255,240,200,0.12)");
		g.addColorStop(1, "rgba(255,240,200,0)");
		ctx.fillStyle = g;
		ctx.fillRect(0, 0, w, h);

		const g2 = ctx.createRadialGradient(x, y, 0, x, y, radius * 0.25);
		g2.addColorStop(0, "rgba(255,255,220,0.3)");
		g2.addColorStop(1, "rgba(255,255,220,0)");
		ctx.fillStyle = g2;
		ctx.fillRect(0, 0, w, h);

		this.baked = layer;
	}
	onResize(w, h) {
		super.onResize(w, h);
		this.place();
		this.bake();
	}
	update(dt) {
		this.pulse += dt * 0.0006;
	}
	draw(ctx) {
		const bloom = 0.22 + 0.18 * Math.sin(this.pulse * 2 * Math.PI);
		ctx.globalAlpha *= bloom;
		ctx.drawImage(this.baked, 0, 0, this.w, this.h);
		ctx.globalAlpha /= bloom;
	}
}


window.addEventListener("DOMContentLoaded", () => {
	try {
		window.weatherSystem = new WeatherSystem("weather-canvas", { transitionDuration: 1500, clearFadeDuration: 600 });

		const cls = (window.weatherSystem && window.weatherSystem.canvas) ? (window.weatherSystem.canvas.className || "") : "";
		const match = cls.match(/weather-([a-z-]+)/);
		if (match) {
			window.weatherSystem.setWeather(match[1]);
		}
	} catch (err) {
		console.error("WeatherSystem init failed:", err);
	}
});
