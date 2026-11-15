// English and Arabic strings, plus number/size/time formatting. No dependencies.
const STR = {
  en: {
    'app.title': 'DropDL Web · Paste a link, get the file',
    'skip': 'Skip to content',
    'aria.theme': 'Toggle light and dark theme',
    'aria.github': 'Source code on GitHub',
    'hero.1': 'Paste a link.', 'hero.2': 'Get the file.',
    'hero.sub': 'Free, no account, no tracking. Pick a format and download straight from your browser.',
    'url.label': 'Link to a video or song',
    'url.placeholder': 'Paste a link from Vimeo, SoundCloud, Dailymotion, archive.org…',
    'url.paste': 'Paste', 'url.go': 'Analyze',
    'limits': 'Up to {height}p · {size} per file · {duration} long · files are deleted after {ttl} minutes',
    'youtube.off': "YouTube blocks free web servers, so it isn't available here. The desktop app supports it.",
    'waking': 'Waking the server up… free servers sleep when idle, this can take up to a minute.',
    'untitled': 'Untitled',
    'paste.denied': "Your browser didn't allow pasting. Press Ctrl+V in the box instead.",
    'kind.video': 'Video', 'kind.audio': 'Audio', 'opt.kind': 'Type',
    'opt.quality': 'Quality', 'opt.format': 'Format', 'opt.best': 'Best available',
    'opt.trim': 'Trim (optional)', 'opt.start': 'Start', 'opt.end': 'End',
    'opt.trim.hint': 'Leave both empty to keep everything. Use 1:23 or seconds. Up to {max}.',
    'trim.bad': "Times aren't valid. Use 1:23 or seconds.", 'trim.order': 'The end must be after the start.',
    'trim.long': 'You can trim up to {max}.', 'trim.needEnd': "Add an end time (this video's length isn't known).",
    'opt.over': 'Over the {size} limit',
    'sum.trimmed': 'trimmed to {len}',
    'btn.download': 'Download', 'btn.save': 'Save file', 'btn.cancel': 'Cancel', 'btn.remove': 'Remove', 'btn.retry': 'Try again',
    'jobs.title': 'Your downloads', 'jobs.empty': 'Nothing yet. Paste a link above.',
    'st.queued': 'Waiting in line · position {n}', 'st.preparing': 'Preparing…', 'st.downloading': 'Downloading {pct}%',
    'st.processing': 'Finishing up…', 'st.done': 'Ready', 'st.cancelled': 'Cancelled', 'st.error': 'Failed', 'st.expired': 'Expired',
    'eta': '{time} left', 'expires': 'Deleted in {time}',
    'cta.title': 'Need YouTube, playlists or the video editor?',
    'cta.body': 'The free desktop app has no limits, handles playlists, auto-retries and includes a full timeline editor.',
    'cta.btn': 'Get the desktop app',
    'foot.legal': "Only download content you own or have permission to save. Follow the source site's terms and your local law.",
    'foot.privacy': 'No accounts, no cookies, no analytics. Files are deleted automatically.',
    'foot.source': 'Open source (MIT)', 'foot.report': 'Report abuse',
    'err.youtube_off': "YouTube isn't available in the web version. The desktop app supports it.",
    'err.youtube_blocked': 'YouTube blocks most free web servers. Try the desktop app, or another site.',
    'err.private': 'That video is private or unavailable.',
    'err.unsupported': "This site isn't supported by the web version.",
    'err.playlist': "Playlists aren't supported in the web version yet. Paste a single video, or use the desktop app.",
    'err.live': "Live streams aren't supported.",
    'err.too_long': 'That video is longer than this server allows ({duration}). You can trim it instead.',
    'err.too_large': 'That file is larger than this server allows ({size}). Try a lower quality or trim it.',
    'err.no_format': "That quality isn't available. Try another.",
    'err.rate_limited': 'Too many requests. Try again in {seconds} seconds.',
    'err.site_rate_limited': 'The site is limiting this server. Try again later.',
    'err.geo': "That content isn't available in this server's region.",
    'err.drm': "That content is DRM-protected and can't be downloaded.",
    'err.network': "Couldn't reach the site. Try again.",
    'err.timeout': 'That took too long and was stopped.',
    'err.busy': 'The server is busy right now. Try again in a minute.',
    'err.storage_full': "The server's storage is full for the moment. Try again in a few minutes.",
    'err.too_many_active': 'You already have downloads in progress. Wait for one to finish.',
    'err.bad_url': "That doesn't look like a valid link.", 'err.bad_scheme': 'Only http:// and https:// links are supported.',
    'err.ip_literal': 'Use the address of the video page, not an IP address.', 'err.bad_port': "That link uses a port that isn't supported.",
    'err.dns_failed': "That website couldn't be found.", 'err.site_blocked': "This site isn't available on this server.",
    'err.bad_clip': 'The trim times are not valid.', 'err.bad_format': "That format isn't available.",
    'err.bad_request': "That request wasn't valid.", 'err.not_found': "This download has expired or doesn't exist.",
    'err.not_ready': "This file isn't ready yet.", 'err.offline': "Couldn't reach the server. Check your connection.",
    'err.failed': 'The download failed.', 'err.cancelled': 'Cancelled.',
    'login.title': 'Enter your access code', 'login.body': 'This is a private DropDL. Ask whoever runs it for the code.',
    'login.label': 'Access code', 'login.go': 'Unlock', 'btn.signout': 'Sign out',
    'err.unauthorized': 'Enter the access code to continue.', 'err.login_failed': "That code isn't right.",
    'err.bad_origin': 'Cross-site requests are not allowed.', 'err.cookies_missing': "The saved cookies file can't be read.",
    'err.youtube_cookies': 'YouTube rejected the saved cookies. Export a fresh cookies.txt from a signed-in browser and restart.',
  },
  ar: {
    'app.title': 'DropDL Web · الصق الرابط واحصل على الملف',
    'skip': 'تخطَّ إلى المحتوى',
    'aria.theme': 'تبديل المظهر الفاتح والداكن',
    'aria.github': 'الشيفرة المصدرية على GitHub',
    'hero.1': 'الصق الرابط.', 'hero.2': 'احصل على الملف.',
    'hero.sub': 'مجاني، بلا حساب وبلا تتبّع. اختر الصيغة ونزّل مباشرةً من متصفحك.',
    'url.label': 'رابط فيديو أو أغنية',
    'url.placeholder': 'الصق رابطًا من Vimeo أو SoundCloud أو Dailymotion أو archive.org…',
    'url.paste': 'لصق', 'url.go': 'تحليل',
    'limits': 'حتى {height}p · {size} للملف · مدة {duration} · تُحذف الملفات بعد {ttl} دقيقة',
    'youtube.off': 'يحظر يوتيوب الخوادم المجانية، لذا هو غير متاح هنا. تطبيق سطح المكتب يدعمه.',
    'waking': 'جارٍ تشغيل الخادم… الخوادم المجانية تنام عند الخمول وقد يستغرق ذلك دقيقة.',
    'untitled': 'بلا عنوان',
    'paste.denied': 'لم يسمح المتصفح باللصق. اضغط Ctrl+V داخل الحقل بدلًا من ذلك.',
    'kind.video': 'فيديو', 'kind.audio': 'صوت', 'opt.kind': 'النوع',
    'opt.quality': 'الجودة', 'opt.format': 'الصيغة', 'opt.best': 'أفضل جودة متاحة',
    'opt.trim': 'قصّ (اختياري)', 'opt.start': 'البداية', 'opt.end': 'النهاية',
    'opt.trim.hint': 'اتركهما فارغين للاحتفاظ بكل شيء. استخدم 1:23 أو ثوانٍ. حتى {max}.',
    'trim.bad': 'الأوقات غير صالحة. استخدم 1:23 أو ثوانٍ.', 'trim.order': 'يجب أن تكون النهاية بعد البداية.',
    'trim.long': 'يمكنك قصّ حتى {max}.', 'trim.needEnd': 'أضف وقت النهاية (مدة هذا الفيديو غير معروفة).',
    'opt.over': 'يتجاوز الحد {size}',
    'sum.trimmed': 'مقصوص إلى {len}',
    'btn.download': 'تنزيل', 'btn.save': 'حفظ الملف', 'btn.cancel': 'إلغاء', 'btn.remove': 'إزالة', 'btn.retry': 'حاول مجددًا',
    'jobs.title': 'تنزيلاتك', 'jobs.empty': 'لا شيء بعد. الصق رابطًا في الأعلى.',
    'st.queued': 'في الانتظار · الترتيب {n}', 'st.preparing': 'جارٍ التحضير…', 'st.downloading': 'جارٍ التنزيل {pct}%',
    'st.processing': 'اللمسات الأخيرة…', 'st.done': 'جاهز', 'st.cancelled': 'أُلغي', 'st.error': 'فشل', 'st.expired': 'انتهت الصلاحية',
    'eta': 'متبقٍّ {time}', 'expires': 'يُحذف خلال {time}',
    'cta.title': 'تحتاج يوتيوب أو قوائم التشغيل أو محرر الفيديو؟',
    'cta.body': 'تطبيق سطح المكتب المجاني بلا حدود، يدعم قوائم التشغيل وإعادة المحاولة التلقائية ويتضمن محرر خط زمني كاملًا.',
    'cta.btn': 'حمّل تطبيق سطح المكتب',
    'foot.legal': 'نزّل فقط المحتوى الذي تملكه أو يُسمح لك بحفظه. التزم بشروط الموقع المصدر وبقوانين بلدك.',
    'foot.privacy': 'لا حسابات ولا ملفات تعريف ارتباط ولا تحليلات. تُحذف الملفات تلقائيًا.',
    'foot.source': 'مفتوح المصدر (MIT)', 'foot.report': 'الإبلاغ عن إساءة',
    'err.youtube_off': 'يوتيوب غير متاح في النسخة الويب. تطبيق سطح المكتب يدعمه.',
    'err.youtube_blocked': 'يحظر يوتيوب معظم الخوادم المجانية. جرّب تطبيق سطح المكتب أو موقعًا آخر.',
    'err.private': 'هذا الفيديو خاص أو غير متاح.',
    'err.unsupported': 'هذا الموقع غير مدعوم في النسخة الويب.',
    'err.playlist': 'قوائم التشغيل غير مدعومة في النسخة الويب بعد. الصق رابط فيديو واحد أو استخدم تطبيق سطح المكتب.',
    'err.live': 'البثوث المباشرة غير مدعومة.',
    'err.too_long': 'هذا الفيديو أطول من الحد المسموح ({duration}). يمكنك قصّه بدلًا من ذلك.',
    'err.too_large': 'الملف أكبر من الحد المسموح ({size}). جرّب جودة أقل أو قصّ المقطع.',
    'err.no_format': 'هذه الجودة غير متاحة. جرّب خيارًا آخر.',
    'err.rate_limited': 'طلبات كثيرة. حاول بعد {seconds} ثانية.',
    'err.site_rate_limited': 'الموقع يحدّ من طلبات هذا الخادم. حاول لاحقًا.',
    'err.geo': 'هذا المحتوى غير متاح في منطقة الخادم.',
    'err.drm': 'المحتوى محمي (DRM) ولا يمكن تنزيله.',
    'err.network': 'تعذّر الاتصال بالموقع. حاول مجددًا.',
    'err.timeout': 'استغرق الأمر وقتًا طويلًا فتم إيقافه.',
    'err.busy': 'الخادم مشغول الآن. حاول بعد قليل.',
    'err.storage_full': 'مساحة الخادم ممتلئة مؤقتًا. حاول بعد بضع دقائق.',
    'err.too_many_active': 'لديك تنزيلات قيد التنفيذ. انتظر حتى ينتهي أحدها.',
    'err.bad_url': 'هذا الرابط غير صالح.', 'err.bad_scheme': 'ندعم روابط http و https فقط.',
    'err.ip_literal': 'استخدم عنوان صفحة الفيديو لا عنوان IP.', 'err.bad_port': 'هذا الرابط يستخدم منفذًا غير مدعوم.',
    'err.dns_failed': 'تعذّر العثور على هذا الموقع.', 'err.site_blocked': 'هذا الموقع غير متاح على هذا الخادم.',
    'err.bad_clip': 'أوقات القص غير صالحة.', 'err.bad_format': 'هذه الصيغة غير متاحة.',
    'err.bad_request': 'طلب غير صالح.', 'err.not_found': 'انتهت صلاحية هذا التنزيل أو أنه غير موجود.',
    'err.not_ready': 'هذا الملف ليس جاهزًا بعد.', 'err.offline': 'تعذّر الوصول إلى الخادم. تحقق من اتصالك.',
    'err.failed': 'فشل التنزيل.', 'err.cancelled': 'أُلغي التنزيل.',
    'login.title': 'أدخل رمز الدخول', 'login.body': 'هذه نسخة خاصة من DropDL. اطلب الرمز ممّن يديرها.',
    'login.label': 'رمز الدخول', 'login.go': 'فتح', 'btn.signout': 'تسجيل الخروج',
    'err.unauthorized': 'أدخل رمز الدخول للمتابعة.', 'err.login_failed': 'هذا الرمز غير صحيح.',
    'err.bad_origin': 'الطلبات القادمة من مواقع أخرى غير مسموحة.', 'err.cookies_missing': 'تعذّرت قراءة ملف ملفات تعريف الارتباط المحفوظ.',
    'err.youtube_cookies': 'رفض يوتيوب ملفات تعريف الارتباط المحفوظة. صدّر ملف cookies.txt جديدًا من متصفح مسجّل الدخول ثم أعد التشغيل.',
  },
};

let lang = 'en';
export const getLang = () => lang;

export function detectLang(saved) {
  if (saved && STR[saved]) return saved;
  return (navigator.language || 'en').toLowerCase().startsWith('ar') ? 'ar' : 'en';
}

export function setLang(next) {
  lang = STR[next] ? next : 'en';
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
}

export function t(key, vars) {
  const text = (STR[lang] && STR[lang][key]) ?? STR.en[key] ?? key;
  return vars ? text.replace(/\{(\w+)\}/g, (_, name) => (vars[name] ?? '')) : text;
}

export function applyStatic() {
  document.title = t('app.title');
  document.querySelectorAll('[data-i18n]').forEach((node) => { node.textContent = t(node.dataset.i18n); });
  document.querySelectorAll('[data-i18n-placeholder]').forEach((node) => { node.placeholder = t(node.dataset.i18nPlaceholder); });
  document.querySelectorAll('[data-i18n-aria]').forEach((node) => { node.setAttribute('aria-label', t(node.dataset.i18nAria)); });
  const label = document.getElementById('lang-label');
  if (label) label.textContent = lang === 'ar' ? 'English' : 'العربية';
}

// Numbers and Latin tokens are wrapped in an LTR isolate so they keep their order inside right-to-left text.
export const ltr = (text) => `⁦${text}⁩`;

function plainBytes(n) {
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = n, i = 0;
  while (value >= 1024 && i < units.length - 1) { value /= 1024; i += 1; }
  const digits = value >= 100 || i === 0 ? 0 : 1;
  return `${new Intl.NumberFormat(lang === 'ar' ? 'ar-u-nu-latn' : 'en', { maximumFractionDigits: digits }).format(value)} ${units[i]}`;
}

export function fmtBytes(n, approx = false) {
  if (n == null || !isFinite(n)) return '';
  return ltr(`${approx ? '~' : ''}${plainBytes(n)}`);
}

export function fmtRate(n) {
  return n == null || !isFinite(n) ? '' : ltr(`${plainBytes(n)}/s`);
}

export function fmtDuration(seconds) {
  if (seconds == null || !isFinite(seconds)) return '';
  const s = Math.max(0, Math.round(seconds)), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const two = (x) => String(x).padStart(2, '0');
  return ltr(h ? `${h}:${two(m)}:${two(sec)}` : `${m}:${two(sec)}`);
}

export function errorText(err, ctx = {}) {
  const code = (err && err.code) || 'failed';
  const key = `err.${code}`;
  const vars = { size: fmtBytes(ctx.maxSize), duration: fmtDuration(ctx.maxDuration), seconds: String(err && err.retryAfter || 0) };
  const known = (STR[lang] && STR[lang][key]) || STR.en[key];
  if (known) return t(key, vars);
  return (err && err.message) || t('err.failed');
}
