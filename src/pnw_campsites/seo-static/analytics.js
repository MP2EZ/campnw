// PostHog for the server-rendered SEO pages.
//
// These pages had no analytics at all, which did more than lose data: a
// visitor landing here from search, then clicking into the SPA, made the SPA
// the first page to initialise PostHog — with document.referrer set to
// campable.co. First-touch attribution was therefore $set_once'd as *internal*
// traffic, so organic search was not merely untracked, it was misfiled.
//
// The loader below is the same stub index.html uses; kept here rather than
// inlined into base.html so there is one copy, and so the SSR responses (which
// Cloudflare caches for an hour) stay small.

!function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.full.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="init capture register register_once register_for_session unregister unregister_for_session getFeatureFlag getFeatureFlagPayload isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSessionId getSurveys getActiveMatchingSurveys renderSurvey canRenderSurvey getNextSurveyStep identify setPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset get_distinct_id getGroups get_session_id get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted captureException loadToolbar get_property getSessionProperty createPersonProfile opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing clear_opt_in_out_capturing debug getPageviewId captureTraceFeedback captureTraceMetric".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);

posthog.init('phc_1csJVtTghShxkA6tijYci9FoTouefkhN1vbrQCj5iDl', {
  api_host: '/ingest',
  ui_host: 'https://eu.posthog.com',
  person_profiles: 'always',
  capture_exceptions: true,
});

(function () {
  var el = document.getElementById('seo-analytics');
  if (!el) return;
  var d = el.dataset;

  var props = { page_type: d.pageType || 'unknown' };
  if (d.state) props.state = d.state;
  if (d.slug) props.slug = d.slug;
  if (d.tag) props.tag = d.tag;
  if (d.campgroundCount) props.campground_count = Number(d.campgroundCount);
  if (d.canonicalUrl) props.canonical_url = d.canonicalUrl;
  posthog.capture('seo_page_viewed', props);

  // Which SSR link sends people into the app, and from which page type.
  document.addEventListener('click', function (ev) {
    var a = ev.target && ev.target.closest && ev.target.closest('a[href]');
    if (!a) return;
    var href = a.getAttribute('href') || '';
    var dest;
    if (href === '/' || href.indexOf('/?') === 0) dest = 'app_search';
    else if (href === '/map') dest = 'map';
    else if (href === '/campgrounds' || href.indexOf('/campgrounds/') === 0) dest = 'campgrounds_index';
    else if (href.indexOf('http') === 0) dest = 'booking_provider';
    else return;
    posthog.capture('seo_cta_clicked', {
      destination: dest,
      page_type: props.page_type,
      slug: props.slug || '',
    });
  });
})();
