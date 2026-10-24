# ShareOne FR: measurable iframe startup and layout lifecycle regression coverage

Status: resolved. [ShareOne PR #318](https://github.com/sudoprivacy/shareone/pull/318)
is deployed to production. Browser acceptance passed on 2026-10-20 and was
repeated on the current production revision on 2026-10-24. The application
defect is fixed in Sudograph. The exact transition behind the original
Northwind observation remains untraced; current ShareOne does not need a
`display: none` change.

## User impact and observed evidence

A reader refreshed the Northwind business review and saw object titles, field
counts and the first field drawn over one another. A deterministic hidden-frame
fixture reproduced the same five parent-title/field intersections with the
previous generated application. The application cached a text height of 16
pixels, including its own padding, instead of the actual multi-line height.
Fitting or zooming the graph after reveal could not repair that cached value.

Sudograph now waits for a measurable canvas/measurement host and ready fonts
before layout. The [implementation](https://github.com/sudoprivacy/sudograph/commit/5a4aa0a6994062c9de499fb2fcb6ceb6c023b7a6)
and [browser receipt](trials/hidden-frame-labels-2026-10-19.json) record:

- The new browser check rejects the old artifact with five header/child overlaps.
- Eight repaired states, including hidden startup, expanded fields, both
  languages and a mobile-width viewport, have no text intersections or text
  outside node bodies.
- Three actual ShareOne reloads of the repaired artifact have no intersections.
  All 48 existing comment threads remain, with no comment mutations.
- Camera pan/zoom causes no graph redraw. This fix does not add continuous
  measurement or a DOM-mutation redraw loop.

These observations establish the failing application mechanism and recovery.
They do not identify a particular ShareOne host operation as the production cause.

## Host code inspection before the change

Read-only inspection of ShareOne main at
[`1212d2ccddd8fa9d786203b034159a7bcf752be3`](https://github.com/sudoprivacy/shareone/blob/1212d2ccddd8fa9d786203b034159a7bcf752be3/frontend/src/pages/share-shell/main.tsx#L851)
finds an absolutely positioned `srcDoc` iframe with `display: "block"`, full
height and a width that changes when reserving comment-sidebar space. Its
`frameReady` state tracks frame load for bridge/comment setup; that alone is
not evidence of a nonzero, settled initial viewport. This inspected Git revision
is not an independently verified deployed image.

Please investigate mount/layout/style readiness, zero-size intermediate states,
sidebar transitions and any other embedding surfaces. Do not replace the
existing `display: "block"` with a supposed fix for code that already uses it.

## Requested generic host behavior

1. Establish a nonzero content wrapper/iframe viewport before starting the
   application document whenever the host is showing a visible page. Distinguish
   document load, measurable layout and an intentionally hidden view.
2. If the host uses a loading cloak, preserve layout geometry where appropriate.
   A correctly sized frame with `visibility: hidden` and a loading overlay is a
   candidate; applying it to arbitrary documents still requires testing. Do not
   rely on a fixed delay or claim every application becomes ready at `load`.
3. Cover nonzero-size restoration and real viewport changes through existing
   browser resize/ResizeObserver behavior and the existing authenticated frame
   bridge where host-specific state is needed. Document any added lifecycle
   notification as an explicit proposed API; none is assumed to exist today.
4. Add a small library-independent fixture that records its initial viewport and
   text geometry. Exercise cold refresh, cached refresh, sidebar open/close,
   narrow viewports, initially hidden/restored content and font readiness.
5. Keep iframe sandboxing, access gates, storage policy, comment anchors and
   hosting behavior intact. Do not reload the application merely to show/hide
   comments or rewrite third-party measurement caches from the host.

The host can reduce a recurring class of chart/editor/embed failures. It cannot
universally repair an application's private layout cache, font timing or hidden
internal tab. Sudograph keeps its own readiness guard regardless of this FR.

## Minimal browser reproduction of the mechanism

Save this as a local HTML file and open it. The inner document measures itself
while its outer iframe is hidden, then the host reveals it. The displayed cached
height remains zero although the visible text now has a positive height. This
is a browser-level reproduction, not proof that current ShareOne uses this host
sequence.

The exact snippet below was executed in an owned Chrome session on 2026-10-20:
`cachedHeight` was `0` and `visibleHeight` was `60` pixels. It has no graph,
framework, third-party library or customer-data dependency.

```html
<!doctype html>
<meta charset="utf-8">
<title>Hidden-frame text measurement</title>
<script>
addEventListener('DOMContentLoaded', () => {
  const frame = document.createElement('iframe');
  frame.style.cssText = 'display:none;width:600px;height:250px';
  frame.srcdoc = '<div id="text" style="line-height:20px">One<br>Two<br>Three</div>' +
    '<pre id="result"></pre><script>' +
    'window.initialHeight=document.getElementById("text").getBoundingClientRect().height;' +
    '</scr' + 'ipt>';
  frame.onload = () => {
    frame.style.display = 'block';
    requestAnimationFrame(() => {
      const doc = frame.contentDocument;
      doc.getElementById('result').textContent = JSON.stringify({
        cachedHeight: frame.contentWindow.initialHeight,
        visibleHeight: doc.getElementById('text').getBoundingClientRect().height
      });
    });
  };
  document.body.append(frame);
});
</script>
```

MDN documents zero layout height for an element hidden with `display: none`,
including through an ancestor. Its `visibility` documentation distinguishes
preserving layout from removing a box:
[offsetHeight](https://developer.mozilla.org/en-US/docs/Web/API/HTMLElement/offsetHeight),
[visibility](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/visibility).
The measured failure above uses `getBoundingClientRect`; its observed zero-size
result is independently reproduced in the Sudograph browser journey.

## Acceptance

Use a visible hosted document and compare its measured startup geometry with a
direct standalone load. Record zero-size observations and the real recovery
event. An intentionally hidden document must receive a usable restoration path;
do not assert that browser-standard hidden measurements should become nonzero.
Keep the application's regression, comment/selection behavior and pan/zoom cost
checked. Include a production deployment/source revision in the host receipt.

## Host investigation and implemented change

A new library-independent fixture reproduced a separate startup defect on the
inspected ShareOne frontend: a normally visible frame's first inline script
observed a `0 x 0` viewport and zero text height. The same document measured
60-pixel text when loaded directly; the hosted document eventually measured
60 pixels in a `1440 x 962` viewport. The visible startup failure reproduced
twice without injecting a hidden ancestor. This establishes a host cold-start
defect, but does not trace the original Northwind production transition.

The content iframe now mounts blank before its application source is assigned.
A startup-only observer requires the actual frame to have the same positive
width and height on two consecutive animation frames. A zero-size frame waits
for native resize observation without timer polling. The observer stops after
startup; opening comments, resizing or hiding an already running application
preserves its document and input state. Document load remains a separate state
associated with the current document identity.

This changes the common HTML/Markdown/text shell, without adding an SDK method,
bridge message, persistent readiness field or application-specific cache fix.
PDF, PowerPoint and Word use other embedding paths and remain unchanged.
Sandbox attributes and existing storage/comment/access contracts remain intact.

Local validation passed 173 frontend unit tests, 13 new lifecycle browser cases,
36 source-attribution cases, the passive object-anchor regression and the
existing long-thread scroll regression. The independent fixture checks cold
and cached startup, sidebar transitions, narrow viewports, delayed real fonts,
initially hidden startup, private/shared data bridges and exact source bytes.
Twenty camera transforms produce no native layout events. Hidden restoration
is checked against an actual viewport change and a trusted native resize;
browsers may pause child `ResizeObserver` delivery while hidden. This does not
promise an event for a hide/reveal that leaves viewport dimensions unchanged.

Sudograph retains its own font and measurement-host guards. A positive outer
iframe cannot establish readiness for an application's internal hidden tabs,
fonts or private layout cache. The ShareOne Skill guidance explains this
distinction without advertising a universal application-ready signal.

## Production acceptance and release

The initial production release is
[`82de0655f99a92a7c867659117ca10eeaa263605`](https://github.com/sudoprivacy/shareone/commit/82de0655f99a92a7c867659117ca10eeaa263605),
with [all seven PR checks green](https://github.com/sudoprivacy/shareone/actions/runs/39365314152),
a [successful deployment](https://github.com/sudoprivacy/shareone/actions/runs/39367006543)
and [public-host parity](https://github.com/sudoprivacy/shareone/actions/runs/39367300496).
Acceptance on 2026-10-24 also covers the subsequent production revision
[`a2408e622dcfdce79b949f6556ed54431544d8fb`](https://github.com/sudoprivacy/shareone/commit/a2408e622dcfdce79b949f6556ed54431544d8fb),
which retains this startup guard and adds the separate share-link navigation
change. Its [deployment](https://github.com/sudoprivacy/shareone/actions/runs/39937813080)
and [host-parity check](https://github.com/sudoprivacy/shareone/actions/runs/40073578912)
also passed.

Owned ai-dev-browser sessions measured the real application and DOM geometry:

| Check | Observed result |
| --- | --- |
| Independent production fixture | All 12 cases passed; the owned share was deleted afterwards. |
| Desktop cold and cached startup | First script saw a `1440 x 962` viewport and 60-pixel text height, matching standalone text height. |
| Narrow cold and cached startup | First script saw a `390 x 806` viewport and the same 60-pixel text height. |
| Sidebar, hidden startup and restoration | Application identity and input state survived; hidden startup assigned no source until positive geometry returned. A viewport change while hidden produced a trusted native resize on restoration. |
| Fonts, bridges and sandbox | Real font readiness, shared/private data operations and unchanged sandbox attributes passed. |
| Original bytes and comments | The 40,584-byte fixture source downloaded exactly; its comment list remained unchanged. |
| Northwind review | All nine states passed: three full loads plus desktop/narrow views with comments open and closed. Actual text rectangles had no intersections, node overflow or header/child intersections. |
| Existing discussions | All 48 threads remained unchanged, with zero comment mutations. All are currently resolved; the check explicitly expanded that group. |
| Camera cost | Twenty fixture transforms produced zero native layout events; 20 Northwind camera updates produced zero graph redraws. |

Sidebar assertions wait for the actual target viewport and sidebar bounds before
checking settled geometry. Screenshots cover the desktop and touch-width views.
Both public hosts are healthy, and the existing paused content-review mode is
unchanged.

[ShareOne Skill 1.11.1](https://github.com/sudoprivacy/shareone-skill/tree/v1.11.1)
contains the measurement guidance and passed its independent tests. Publication
completed on [ClawHub](https://github.com/sudoprivacy/shareone-skill/actions/runs/39367153156),
[SkillHub](https://github.com/sudoprivacy/shareone-skill/actions/runs/39367153095)
and [Sudohub](https://github.com/sudoprivacy/shareone-skill/actions/runs/39367153128).
The live ShareOne download was checked against the released Skill metadata and
workflow text.
