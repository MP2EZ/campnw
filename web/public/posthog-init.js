// PostHog loader + config. A file rather than an inline <script> so the CSP
// can drop script-src 'unsafe-inline' (SEC-12). Loaded as a classic blocking
// script in <head>, so window.posthog exists before the app bundle runs.
!function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.full.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="init capture register register_once register_for_session unregister unregister_for_session getFeatureFlag getFeatureFlagPayload isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSessionId getSurveys getActiveMatchingSurveys renderSurvey canRenderSurvey getNextSurveyStep identify setPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset get_distinct_id getGroups get_session_id get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted captureException loadToolbar get_property getSessionProperty createPersonProfile opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing clear_opt_in_out_capturing debug getPageviewId captureTraceFeedback captureTraceMetric".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);
(function () {
  // The native shells serve this page from capacitor://localhost (iOS) or
  // https://localhost (Android), where a relative /ingest doesn't exist and
  // PostHog never loaded. They use the campable.co proxy directly (its CORS
  // allows both origins).
  var phNative = location.protocol === 'capacitor:' || (location.protocol === 'https:' && location.hostname === 'localhost');

  // Search URLs carry the origin address and the natural-language query. The
  // server keeps custom addresses out of its logs; keep them out of analytics
  // too. Known bases (web/src/lib/bases.ts) are kept. SEC-16.
  var KNOWN_BASES = ['seattle', 'bellevue', 'portland', 'spokane', 'bellingham', 'bend', 'bozeman', 'missoula', 'jackson', 'sacramento', 'reno', 'moscow'];
  var URL_PROPS = ['$current_url', '$referrer', '$initial_current_url', '$initial_referrer'];

  function scrubUrl(value) {
    if (typeof value !== 'string') return value;
    var url;
    try { url = new URL(value); } catch (e) { return value; }
    ['from', 'from_location'].forEach(function (key) {
      var v = url.searchParams.get(key);
      if (v && KNOWN_BASES.indexOf(v.toLowerCase()) === -1) url.searchParams.set(key, 'custom');
    });
    if (url.searchParams.get('q')) url.searchParams.set('q', 'redacted');
    return url.toString();
  }

  function scrubProps(props) {
    if (!props) return;
    URL_PROPS.forEach(function (key) {
      if (key in props) props[key] = scrubUrl(props[key]);
    });
  }

  posthog.init('phc_1csJVtTghShxkA6tijYci9FoTouefkhN1vbrQCj5iDl', {
    api_host: phNative ? 'https://campable.co/ingest' : '/ingest',
    ui_host: 'https://eu.posthog.com',
    person_profiles: 'always',
    capture_exceptions: true,
    session_recording: {
      maskAllInputs: true,
    },
    before_send: function (event) {
      if (event) {
        scrubProps(event.properties);
        scrubProps(event.$set);
        scrubProps(event.$set_once);
      }
      return event;
    },
  });
})();
