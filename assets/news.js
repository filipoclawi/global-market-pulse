(() => {
  'use strict';
  const STORAGE_KEY = 'global-market-pulse:news-state:v1';
  const $ = id => document.getElementById(id);
  let payload = { stories: [], archive: [] }, activeFilter = 'all';
  const expanded = new Set();
  const state = loadState();

  function loadState() {
    try {
      const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
      return { read: new Set(Array.isArray(value.readIds) ? value.readIds : []), starred: new Set(Array.isArray(value.starredIds) ? value.starredIds : []) };
    } catch (_) { return { read: new Set(), starred: new Set() }; }
  }
  function saveState() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ readIds: [...state.read], starredIds: [...state.starred] })); } catch (_) {}
  }
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  function safeUrl(value) { try { const url = new URL(value); return url.protocol === 'https:' ? url.href : '#'; } catch (_) { return '#'; } }
  function prettyDate(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('en', { month:'short', day:'numeric', year:'numeric', timeZone:'UTC' }).format(date); }
  function relativeTime(value) {
    const date = new Date(value), mins = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
    return mins < 2 ? 'just now' : mins < 60 ? `${mins}m ago` : mins < 1440 ? `${Math.round(mins/60)}h ago` : `${Math.round(mins/1440)}d ago`;
  }

  function setTab(name, updateHash = true) {
    const news = name === 'news';
    $('news-panel').hidden = !news; $('markets-panel').hidden = news;
    for (const [buttonName, button] of [['news',$('tab-news')],['markets',$('tab-markets')]]) {
      const selected = buttonName === name;
      button.classList.toggle('active', selected); button.setAttribute('aria-selected', String(selected)); button.tabIndex = selected ? 0 : -1;
    }
    if (updateHash && location.hash !== `#${name}`) history.replaceState(null, '', `#${name}`);
    if (!news) requestAnimationFrame(() => window.dispatchEvent(new CustomEvent('market-panel-shown')));
  }

  function bindTabs() {
    const tabs = [$('tab-news'), $('tab-markets')];
    tabs.forEach(button => button.addEventListener('click', () => setTab(button.id === 'tab-news' ? 'news' : 'markets')));
    document.querySelector('.workspace-tabs').addEventListener('keydown', event => {
      const current = tabs.indexOf(document.activeElement); if (current < 0) return;
      let next = current;
      if (event.key === 'ArrowRight') next = (current + 1) % tabs.length;
      else if (event.key === 'ArrowLeft') next = (current - 1 + tabs.length) % tabs.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = tabs.length - 1;
      else return;
      event.preventDefault(); tabs[next].focus(); tabs[next].click();
    });
    window.addEventListener('hashchange', () => setTab(location.hash === '#markets' ? 'markets' : 'news', false));
    setTab(location.hash === '#markets' ? 'markets' : 'news', false);
  }

  function visibleStories() {
    if (activeFilter === 'starred') return [...payload.stories, ...(payload.archive || [])].filter(story => state.starred.has(story.id));
    if (activeFilter === 'unread') return payload.stories.filter(story => !state.read.has(story.id) || expanded.has(story.id));
    return payload.stories;
  }
  function renderCounts() {
    const unread = payload.stories.filter(story => !state.read.has(story.id)).length;
    const starred = [...payload.stories, ...(payload.archive || [])].filter(story => state.starred.has(story.id)).length;
    $('tab-unread-count').textContent = unread; $('tab-unread-count').setAttribute('aria-label', `${unread} unread`);
    $('filter-unread-count').textContent = unread; $('filter-starred-count').textContent = starred;
    $('mark-all-read').disabled = unread === 0;
  }
  function storyMarkup(story) {
    const isRead = state.read.has(story.id), isStarred = state.starred.has(story.id), isExpanded = expanded.has(story.id);
    const tags = story.tags.map(tag => `<span>${escapeHtml(tag)}</span>`).join('');
    return `<article class="news-story${isRead ? ' is-read' : ' is-unread'}${isStarred ? ' is-starred' : ''}" data-story-id="${escapeHtml(story.id)}">
      <div class="story-row">
        <button class="story-toggle" type="button" aria-expanded="${isExpanded}" aria-controls="story-body-${escapeHtml(story.id)}">
          <span class="unread-dot" aria-label="${isRead ? 'Read' : 'Unread'}"></span>
          <span class="story-main">
            <span class="story-kicker"><time datetime="${escapeHtml(story.publishedAt)}">${prettyDate(story.publishedAt)}</time><span>${escapeHtml(story.readingMinutes)} min read</span></span>
            <strong class="story-title">${escapeHtml(story.title)}</strong>
            <span class="story-preview">${escapeHtml(story.preview)}</span>
          </span>
          <span class="story-chevron" aria-hidden="true">⌄</span>
        </button>
        <div class="story-actions">
          <button class="read-toggle" type="button" aria-label="${isRead ? 'Mark unread' : 'Mark read'}: ${escapeHtml(story.title)}" title="${isRead ? 'Mark unread' : 'Mark read'}">${isRead ? '↶' : '✓'}</button>
          <button class="star-toggle" type="button" aria-label="${isStarred ? 'Remove star' : 'Add star'}: ${escapeHtml(story.title)}" aria-pressed="${isStarred}" title="${isStarred ? 'Remove star' : 'Add star'}">${isStarred ? '★' : '☆'}</button>
        </div>
      </div>
      <div class="story-source-row">
        <a class="source-link" href="${safeUrl(story.sourceUrl)}" target="_blank" rel="noopener noreferrer">Source · ${escapeHtml(story.sourceLabel)} <span aria-hidden="true">↗</span></a>
      </div>
      <div id="story-body-${escapeHtml(story.id)}" class="story-body" ${isExpanded ? '' : 'hidden'}>
        <div class="story-tags">${tags}</div>
        <p>${escapeHtml(story.summary)}</p>
        <div class="long-term-lens"><b>Long-term lens</b><p>${escapeHtml(story.whyItMatters)}</p></div>
      </div>
    </article>`;
  }
  function renderStories(focus = {}) {
    const stories = visibleStories();
    $('news-list').innerHTML = stories.map(storyMarkup).join('');
    $('news-empty').hidden = stories.length > 0;
    if (!stories.length) {
      const copy = activeFilter === 'unread' ? ['You’re all caught up.','There are no unread stories in this briefing.'] : activeFilter === 'starred' ? ['No starred stories yet.','Use the star beside an article to save it for up to six months.'] : ['No news is available right now.','The last valid briefing will return when sources recover.'];
      $('news-empty').querySelector('strong').textContent = copy[0]; $('news-empty').querySelector('span').textContent = copy[1];
    }
    renderCounts();
    if (focus.message) $('news-status').textContent = focus.message;
    if (focus.id || Number.isInteger(focus.index)) requestAnimationFrame(() => {
      const same = focus.id ? $('news-list').querySelector(`[data-story-id="${CSS.escape(focus.id)}"] ${focus.selector || '.story-toggle'}`) : null;
      const rows = [...$('news-list').querySelectorAll('[data-story-id]')];
      const nearby = rows[Math.min(focus.index || 0, Math.max(0, rows.length - 1))]?.querySelector(focus.selector || '.story-toggle');
      (same || nearby || document.querySelector(`[data-news-filter="${activeFilter}"]`))?.focus();
    });
  }
  function renderFreshness() {
    $('news-checked-relative').textContent = relativeTime(payload.checkedAt || payload.generatedAt);
    $('news-data-as-of').textContent = `Stories through ${prettyDate(`${payload.dataAsOf}T00:00:00Z`)}`;
    const stale = payload.staleSources?.length || 0, briefingStale = payload.briefingStale === true;
    document.querySelector('.news-freshness').classList.toggle('is-stale', briefingStale);
    $('news-stale-warning').hidden = !briefingStale && stale === 0;
    $('news-stale-warning').textContent = briefingStale ? 'Briefing is stale · showing the last valid stories' : stale ? `${stale} source${stale === 1 ? '' : 's'} unavailable` : '';
  }
  function bindNewsControls() {
    document.querySelector('.news-filters').addEventListener('click', event => {
      const button = event.target.closest('[data-news-filter]'); if (!button) return;
      activeFilter = button.dataset.newsFilter;
      document.querySelectorAll('[data-news-filter]').forEach(item => { const active = item === button; item.classList.toggle('active', active); item.setAttribute('aria-pressed', String(active)); });
      renderStories();
    });
    $('mark-all-read').addEventListener('click', () => { payload.stories.forEach(story => state.read.add(story.id)); expanded.clear(); saveState(); renderStories({message:'All current stories marked read.'}); });
    $('news-list').addEventListener('click', event => {
      const article = event.target.closest('[data-story-id]'); if (!article) return;
      const id = article.dataset.storyId, index = [...$('news-list').querySelectorAll('[data-story-id]')].indexOf(article), story = [...payload.stories,...(payload.archive || [])].find(item => item.id === id), title = story?.title || 'Article';
      if (event.target.closest('.star-toggle')) {
        const removing=state.starred.has(id); removing ? state.starred.delete(id) : state.starred.add(id); saveState(); renderStories({id,index,selector:'.star-toggle',message:`${title} ${removing ? 'removed from' : 'added to'} Starred.`}); return;
      }
      if (event.target.closest('.read-toggle')) {
        const markingUnread=state.read.has(id); markingUnread ? state.read.delete(id) : state.read.add(id); expanded.delete(id); saveState(); renderStories({id,index,selector:'.read-toggle',message:`${title} marked ${markingUnread ? 'unread' : 'read'}.`}); return;
      }
      if (event.target.closest('.story-toggle')) {
        const closing=expanded.has(id); if (closing) expanded.delete(id); else { expanded.add(id); state.read.add(id); saveState(); }
        renderStories({id,index,selector:'.story-toggle',message:closing ? `${title} collapsed.` : `${title} opened and marked read.`});
      }
    });
  }

  async function initNews() {
    bindTabs(); bindNewsControls();
    try {
      const response = await fetch(`data/economic-news.json?v=${Date.now()}`); if (!response.ok) throw new Error(`HTTP ${response.status}`);
      payload = await response.json(); if (!Array.isArray(payload.stories) || !payload.stories.length) throw new Error('No news stories');
      renderFreshness(); renderStories(); document.documentElement.dataset.newsReady = 'true';
    } catch (error) {
      console.error('News initialization failed', error); $('news-list').innerHTML = '<div class="news-load-error">The weekly briefing could not be loaded. Market data is still available in the Markets tab.</div>'; document.documentElement.dataset.newsReady = 'error';
    }
  }
  initNews();
})();
