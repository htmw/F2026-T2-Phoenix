const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const http = require("http");
const https = require("https");
const { URL } = require("url");

const CHROME =
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const OUT = path.resolve(__dirname, "../../docs/images");
const PORT = 9229;

fs.mkdirSync(OUT, { recursive: true });

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function getJson(url) {
  return new Promise((resolve, reject) => {
    http
      .get(url, (res) => {
        let raw = "";
        res.on("data", (c) => (raw += c));
        res.on("end", () => {
          try {
            resolve(JSON.parse(raw));
          } catch (e) {
            reject(e);
          }
        });
      })
      .on("error", reject);
  });
}

async function main() {
  const chrome = spawn(
    CHROME,
    [
      `--remote-debugging-port=${PORT}`,
      "--headless=new",
      "--disable-gpu",
      "--hide-scrollbars",
      "--window-size=1440,920",
      "--user-data-dir=/tmp/agent-mesh-chrome-shots",
      "about:blank",
    ],
    { stdio: "ignore" },
  );

  await sleep(1500);

  const CDP = (await import("chrome-remote-interface")).default;
  const client = await CDP({ port: PORT });
  const { Page, Runtime, Emulation, Network } = client;
  await Promise.all([Page.enable(), Runtime.enable(), Network.enable()]);
  await Emulation.setDeviceMetricsOverride({
    width: 1440,
    height: 920,
    deviceScaleFactor: 2,
    mobile: false,
  });

  async function hideOverlays() {
    await Runtime.evaluate({
      expression: `(() => {
        document.querySelectorAll('nextjs-portal').forEach(e => e.remove());
        if (!document.getElementById('shot-hide')) {
          const s = document.createElement('style');
          s.id = 'shot-hide';
          s.textContent = \`
            nextjs-portal,[data-next-badge-root],[data-nextjs-toast]{display:none!important}
            html{scroll-behavior:auto!important}
            *,*::before,*::after{animation:none!important;transition:none!important}
          \`;
          document.head.appendChild(s);
        }
        try {
          localStorage.setItem('agent-mesh-theme', 'light');
          document.documentElement.dataset.theme = 'light';
          document.documentElement.dataset.themePreference = 'light';
          document.documentElement.style.colorScheme = 'light';
        } catch (e) {}
        return true;
      })()`,
    });
  }

  async function setNavVisible(visible) {
    await Runtime.evaluate({
      expression: `(() => {
        const header = document.querySelector('header.mkt-nav') || document.querySelector('header');
        if (header) header.style.setProperty('display', ${JSON.stringify(visible ? "" : "none")}, 'important');
        return !!header;
      })()`,
    });
  }

  async function goto(url) {
    await Page.navigate({ url });
    await Page.loadEventFired();
    await sleep(1600);
    await hideOverlays();
    await sleep(300);
  }

  async function shotClip(file, clip) {
    const { data } = await Page.captureScreenshot({
      format: "jpeg",
      quality: 92,
      clip: { ...clip, scale: 1 },
      captureBeyondViewport: true,
      fromSurface: true,
    });
    fs.writeFileSync(path.join(OUT, file), Buffer.from(data, "base64"));
    console.log("ok", file, clip.width + "x" + clip.height);
  }

  async function sectionClip(selector) {
    const { result } = await Runtime.evaluate({
      expression: `(() => {
        const el = document.querySelector(${JSON.stringify(selector)});
        if (!el) return null;
        el.scrollIntoView({ block: 'start' });
        const r = el.getBoundingClientRect();
        return {
          x: Math.max(0, Math.floor(r.left)),
          y: Math.max(0, Math.floor(window.scrollY + r.top)),
          width: Math.ceil(r.width),
          height: Math.ceil(r.height),
        };
      })()`,
      returnByValue: true,
    });
    return result.value;
  }

  async function heroClip() {
    const { result } = await Runtime.evaluate({
      expression: `(() => {
        window.scrollTo(0,0);
        const hero = document.querySelector('section.mkt-hero');
        const r = hero.getBoundingClientRect();
        return {
          x: 0,
          y: 0,
          width: Math.ceil(document.documentElement.clientWidth),
          height: Math.ceil(r.bottom),
        };
      })()`,
      returnByValue: true,
    });
    return result.value;
  }

  // Marketing
  await goto("http://localhost:3000/");
  await setNavVisible(true);
  await shotClip("01-hero.jpg", await heroClip());
  for (const [sel, file] of [
    ["#agents", "02-agents.jpg"],
    ["#how-it-works", "03-workflow.jpg"],
    ["#communication", "04-communication.jpg"],
    ["#workspace", "05-workspace.jpg"],
  ]) {
    await goto("http://localhost:3000/");
    await setNavVisible(false);
    await sleep(200);
    const clip = await sectionClip(sel);
    if (!clip) throw new Error("missing " + sel);
    await sleep(400);
    await shotClip(file, clip);
  }

  // Office
  await goto("http://localhost:3000/office");
  await setNavVisible(true);
  await Runtime.evaluate({ expression: "window.scrollTo(0,0)" });
  await sleep(400);
  const { data: officeData } = await Page.captureScreenshot({
    format: "jpeg",
    quality: 92,
    fromSurface: true,
  });
  fs.writeFileSync(path.join(OUT, "06-office.jpg"), Buffer.from(officeData, "base64"));
  console.log("ok 06-office.jpg");

  // Settings — taller viewport so provider grid isn't clipped mid-row
  await Emulation.setDeviceMetricsOverride({
    width: 1440,
    height: 1100,
    deviceScaleFactor: 2,
    mobile: false,
  });
  await goto("http://localhost:3000/office");
  await Runtime.evaluate({
    expression: `(() => {
      const btn = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Settings');
      if (btn) btn.click();
      return !!btn;
    })()`,
  });
  await sleep(1000);
  await hideOverlays();
  await Runtime.evaluate({ expression: "window.scrollTo(0,0)" });
  const { data: settingsData } = await Page.captureScreenshot({
    format: "jpeg",
    quality: 92,
    fromSurface: true,
  });
  fs.writeFileSync(path.join(OUT, "07-settings.jpg"), Buffer.from(settingsData, "base64"));
  console.log("ok 07-settings.jpg");

  await client.close();
  chrome.kill("SIGKILL");
  // cleanup leftover png
  const png = path.join(OUT, "01-hero.png");
  if (fs.existsSync(png)) fs.unlinkSync(png);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
