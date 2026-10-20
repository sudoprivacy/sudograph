# ShareOne FR: measurable iframe startup and layout lifecycle regression coverage

Status: proposed host compatibility improvement. The application defect is
fixed in Sudograph. The exact ShareOne production transition that caused the
original zero-size observation has not been traced. This is not a confirmed
claim that current ShareOne applies `display: none` to its content frame.

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

## Current host code inspection

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
