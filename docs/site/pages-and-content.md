# Pages and content

Everything editors write and visitors read, apart from appeals and the Donate page
([Appeals and giving](appeals-and-giving.md)). Each section says what the page or feature does,
why, and where its code is.

## Every page

Every page shares one layout (`charity/templates/base.html`):

- **Announcement banner** (when switched on), then the **header**: the charity's name on a row of
  its own, then Menu, the main menu and search, the language switch and Donate
  ([Look and feel](look-and-feel.md#header)).
- **Main content**, with a "Skip to content" link before the header.
- **Footer**: the charity's name, its registration line (each line as the charity typed it, left
  out while there's none), address, email, phone and social links, the privacy notice link, and
  "© year, name.", all from Site settings. A long number or email breaks to fit a phone. On a
  short page it sits at the bottom of the window.
- In `<head>`: the title (the page's SEO title or title, then "| the charity's name" in the
  language being read, [Languages](languages.md#snippets-and-settings-text)), its search
  description, social sharing tags and links to its translations
  ([SEO and sharing](#seo-and-sharing)).

The **main menu** is the standard's five sections, About us, Appeals, Stories, Get involved and
Contact, named by the standard in the language being read, never by page titles
([Standard](standard.md#the-menu)). A moderator chooses the page each one links to in **Site
settings → Menu**, which names each section the menu leaves out: not set, not published, or not
public (behind a password or login). Only the chosen page decides that, so a section is shown or
left out in every language alike, as the tab says. Each links to its page's published, public
translation in the language being read, else to the chosen page, and the current page and section are marked for
screen readers (`{% main_menu %}`, `core/templatetags/navigation_tags.py`, with the sections in
`core/menu.py`). With no section shown there's no menu at all. "Show in menus" adds nothing to it
yet.

## A new site's home page

While a home page's hero heading, hero text and body are all empty, in any language, it shows
only the charity's name, "Our new website is on its way." and the main email and phone as links,
and it stays out of search results. A hero image alone doesn't end this. Writing any of the three
does, at once. `new_site` leaves both home pages this way ([Hosting](../hosting.md#management-commands)).

The other standard pages start as drafts, so the menu starts empty and fills as About us, Appeals
and Stories are published, and the header has no Donate button until the Donate page is live.

## Pages still to write

The top of the admin's dashboard lists what's left of the [standard](standard.md#pages-every-site-has)
on the site, on every site, however it was built: "Pages still to write: 4 of 16", counting each
standard page with a page type today once per language. Rows are grouped by language, main
language first: the privacy notice, Donate, the menu sections in the standard's order, then the
volunteer form and the accessibility statement. Each is the
page's title, linked to edit it if you may, and one status: **Not set**, **Draft**, **Has [Write:
…] text**, **Not translated yet** with a Translate link, or **Translate after publishing** while
the main page isn't set or live. The privacy notice, Donate, About us, Appeals, Stories and Contact
are the pages chosen in Site settings (Not set links there); the volunteer form is found by its address
under the home page until it has a chooser of its own, and the accessibility statement by its
address too, since a home page has only one. A line above the list asks for the registration details while Site
settings' registration line is blank in any language.

Only someone who can change a page or Site settings sees the panel; a pledges-only user can do
nothing it asks.

Nothing is stored: unpublishing a page, or an upgrade adding a standard page, brings its row back.
With nothing left, a site `new_site` built says "Every standard page is written and published." for
7 days after the last one first went live (republishing a page later doesn't bring it back); it
knows from an entry `new_site` writes in the home page's History. Any other site shows no panel, so
it's never told it's done.

## What stops a page going live

A few mistakes would put something untrue or unlawful on a live site, so the admin refuses to
publish a page (`core/publishing.py`):

- **while it holds placeholder text**, one line in square brackets starting "[Write:" (or
  "[लेख्नुहोस्:"), which tells the editor what only the charity can write
  ([The charity site standard](standard.md#how-its-kept)). Other brackets, such as "[1]", are
  fine;
- **while it's a form or the Donate page and the privacy notice chosen in Site settings isn't
  published**, because a page that collects personal details must say how they're used
  ([Appeals and giving](appeals-and-giving.md#privacy-notice));
- **while it's a form or the Donate page and Site settings' registration line is blank in any
  language**, because a page asking for gifts or details must show the charity is registered.
  Pages already live stay live, and other pages, home pages included, still publish;
- **while it's a form with no email address to send each message to**, or nobody would read them.

Drafts always save. Every way a page goes live asks the same check:

| Route | When it's refused |
|---|---|
| Publish, or Submit for moderation, in the editor | The error is on the field, or on the block in a body, and the banner says the page can't go live yet, the changes are still there and it can be saved as a draft, in place of Wagtail's "could not be saved" or, on a new page, "could not be created" |
| Approving a workflow task | The page's edit view says why; the task waits to be approved again |
| Bulk publish | The chosen pages, and their subpages when included, are checked first: one refusal and nothing is published, with each page named. Each is checked as the site is now, so a form chosen with the privacy notice is refused: publish the notice on its own first |
| A go-live time | The page stays a draft with its go-live time cleared, from its draft too; its History and the server log say why, and the pages after it still go live |
| Code | `publish()` raises `PublishRefused` |

The other way round, **the chosen privacy notice can't be unpublished while any form or Donate
page on its site is live**, in either language: "Unpublish these forms first: …", naming them.
That holds for Unpublish in the editor (with its subpages too), bulk unpublish (nothing is
unpublished), an expiry time (the notice stays live with its expiry cleared, and its History and
the server log say why) and code (`unpublish()` raises `UnpublishRefused`). Forms going offline
with the notice don't count: those among the subpages or pages unpublished in the same action,
or whose expiry time passes in the same run as the notice's. So a whole site, notice and forms,
can be unpublished in one step; the refusal names only the forms that would stay live.

Not guarded: the publish and unpublish actions of Wagtail's admin API
(`/admin/api/main/pages/<id>/action/publish/` and `…/unpublish/`), which no admin screen uses,
and deleting the privacy notice or choosing another in Site settings while forms are live.

## Home page

The first thing a visitor sees, so it leads with the charity's message and its open appeals
(`home/models.py`, `HomePage`):

- **A banner**: a photo with the heading (the page title if left blank), a line of text and a
  button to a chosen page. Phones get a square crop of the photo and wider screens a wide one
  ([Images](images.md#the-homepage-banner)).
- **Current appeals**: the three newest open appeals (by start date) that are public and in the
  page's language, as cards. Hidden when there are none.
- **The body**: any content blocks.

## Standard pages

General pages such as About us or the privacy notice: a title, an introduction and a body of
content blocks. They go under the home page or another standard page, so editors can build
sections (`home/models.py`, `StandardPage`).

## The accessibility statement

`AccessibilityStatementPage` (`home/models.py`) is the standard's accessibility statement
([Standard](standard.md#the-accessibility-statement)): one under each home page, at
`/accessibility/` in a new site. There's no chooser: the footer links to the one under the home
page in the language being read once it's live and public, else to the main language's, last in
its list, found in the same query as the chosen pages (`core/context_processors.py`).

- **The platform's part is in the code** (`core/accessibility.py`), translated, the same on
  every site: that the site partially conforms to WCAG 2.2 AA, the checks behind that
  (`CHECKS`), the known problems in the website itself (`KNOWN_PROBLEMS`) and the day they were
  last reviewed (`REVIEWED`). A fix to a listed problem takes it off the list in the same pull
  request, and each release checks the list and moves the date
  ([Releases](../contributing/releases.md#cutting-a-release)), so every site's statement is
  corrected at its next upgrade.
- **The charity writes three things:** a one-line commitment under the title, a list of
  problems in what it has published (such as a PDF or a video without captions), and the day it
  last checked its content. The list and the date show only when filled in. A new site's draft
  has a commitment and a placeholder in the list, so it can't go live until the charity writes
  its problems or deletes the line.
- **Tell us about a problem** shows the phone, email and address from Site settings and a link
  to the Contact page when it's live and public; it's left out when there's none of them.

## Content blocks

Every page body is a StreamField of the same blocks, so editors compose pages the same way
everywhere (`core/blocks.py`, `BaseStreamBlock`; templates in `core/templates/core/blocks/`):

| Block | What editors get |
|---|---|
| Heading | Heading text at level 2, 3 or 4 |
| Paragraph | Rich text: headings, bold, italic, a pale amber **Highlight**, links, document links and lists. Highlight is this site's own button (`core/wagtail_hooks.py`), for the one phrase a reader mustn't miss |
| Image | A photo with an optional caption; its credit shows under it |
| Quote | Quote text and an optional attribution |
| Call to action | A title, text and a button to a page **or** a web address, never both and never neither (checked when saving) |
| Impact statistics | An optional heading and one to four figures with labels, such as "412 wells built" |
| Video | A YouTube or Vimeo link, embedded |
| Table | A table editors fill in |
| Document | A download link for an uploaded document, with optional link text |
| Testimonial | A chosen testimonial (below) |
| Partners | Every partner's logo, with an optional heading |

## Partners and testimonials

Reusable content that isn't a page, under **Supporters** in the admin (`core/models.py`,
`core/wagtail_hooks.py`):

- **Partners**: organisations that fund or work with the charity: name, website and logo. Editors
  drag them into order; the Partners block shows them all, each in the language being read.
- **Testimonials**: a quote from a beneficiary, volunteer or supporter, with their name, role and
  photo. They quote real people, so they have drafts, revisions, locking and preview, and a
  moderator publishes them ([Editors and permissions](editors-and-permissions.md)).

Both are translated with **Translate**, and a page shows each in its own language, else in the
main language ([Languages](languages.md#snippets-and-settings-text)).

## Site settings and the banner

Settings that apply to every page, under **Settings** in the admin (`core/models.py`):

- **Site settings** (moderators only, because they hold the charity's identity): the charity's
  **name** (in the header, the footer and the tab title), its **registration line** (under the
  name in the footer: where it's registered and its numbers, typed by the charity), its address
  and its **refund policy**
  ([Appeals and giving](appeals-and-giving.md#paying-a-pledge)), each written in each
  language (the registration line in every language before the settings can be saved, though a
  preview works without it; the address and refund policy in every language or none); contact email and phone (shown in the footer); **We take gifts at our office**, which offers paying in person after a pledge, with that address and phone ([Appeals and giving](appeals-and-giving.md#paying-a-pledge)); the **Donate page** the header's button goes to; the **privacy notice** ([Appeals and giving](appeals-and-giving.md#privacy-notice));
  the **currency** every amount is shown in ([Money](appeals-and-giving.md#money)); the
  **default phone country**, where the Donate and Contact forms' country picker starts and how
  the Contact page dials a number written the local way; Facebook, Instagram and LinkedIn
  links (each shown in the footer only when set); and, on the **Brand** tab, the charity's
  [logo](look-and-feel.md#the-logo), shown beside its name in the header, at a size it chooses,
  its main and accent
  colours ([Look and feel](look-and-feel.md#brand-colours)), a light or dark name bar and
  footer ([Look and feel](look-and-feel.md#a-light-or-dark-name-bar-and-footer)) and a
  [font style](look-and-feel.md#a-font-style). A
  change shows on every page as soon as it's saved, so its preview panel shows it on real pages
  first ([Look and feel](look-and-feel.md#seeing-a-brand-change-before-it-goes-live)).
- **Announcement banner**: one message, written in each language, on or off, optionally linking
  to a page, shown across the top of every page in amber. Editors change it directly, without
  approval, because an emergency appeal can't wait.

Both are per Site. Text that differs between languages is in rows, one per language, in the same
form, and links to chosen pages go to their translation in the language being read
([Languages](languages.md#snippets-and-settings-text)).

## Forms

Editors build forms themselves, such as volunteer sign-up, with Wagtail's form builder
(`contact/models.py`, `FormPage`): an introduction, the fields, a thank-you message, and who is
emailed about each submission. What every form page does lives once in the abstract
`EmailFormPage`, which `FormPage` and `ContactPage` inherit; a new form page type inherits it too,
and declares what the base can't: its own field model (a `ParentalKey` with
`related_name="form_fields"`) and its own form and thank-you templates.
`contact/tests/test_form_page.py` fails for a type without them.

- After a send, the page goes on to `?sent` at the address the form was sent to (a 303
  redirect), which shows the thank-you message. Reloading it can't send the message twice, and
  opening `?sent` directly saves and sends nothing. The thank-you carries `noindex`, so search
  engines list only the form.
- The email's **Reply-To** is the sender's email field, so the team can answer directly. The
  email is written in the site's main language, which the team reads, whichever language the
  sender wrote in.
- If the email can't be sent, the error is logged and the visitor still sees the thank-you page:
  the submission is already saved, and the team reads and exports submissions (CSV or Excel) in the admin. Anything a visitor typed
  that a spreadsheet would run as a formula is exported as text.
- "How we use your details" links to the privacy notice just before the Send button.
- Only the page's data fields (`get_data_fields()`) are saved, emailed and exported, so a field
  that only helps fill in another, like the phone's country, never reaches a submission.

### The Contact page

`ContactPage` is the standard's Contact page ([Standard](standard.md#the-contact-page)): one
under each home page, chosen for the menu's Contact section, which takes no other kind of page.
The footer links to it once it's live and public, after the privacy notice and before the
accessibility statement. Its form starts with
a **fixed core** (`ContactForm`): Your name, Email, Phone with its country (the shared picker in
`core/phone.py`, `includes/phone_field.html`) and Your message, saved as `name`, `email`, `phone`
and `message` in every language, the phone in E.164 (+977…). Email or phone is required. A
message is at most 2,000 characters, with the same count below the box as Donate's message
(`core/textarea.py`). The
editor's **extra questions** follow; one named like a core field (or `submit_time`) is refused in
the admin. Each language's page keeps its own messages and its own extra questions.

- **General enquiries** come from Site settings: the phone, linked with `tel_href`
  (`core/templatetags/phone_tags.py`), which adds the site's phone country to a number written
  the local way and links the first of several; text with no number it can read is shown
  without a link. Then the email and the address, with **Open in a map** under it when Site
  settings has a **Map link** (Organisation tab): a link the charity pastes from Google Maps or
  OpenStreetMap, https only (`HttpsURLField`, `core/fields.py`). There's no embedded map and no
  link built from the address text, which in Nepal is often too informal for a map search.
- **Other contacts** are teams such as Finance or Volunteering (`ContactTeam`, the page's
  **Other contacts** panel): a name and an email or phone, at least one. They're part of the
  page, so Translate copies them and each language keeps its own. Shown after General
  enquiries, in the same column, as H2 Other contacts with each team's name as an H3, and left
  out when there are none.
- The thank-you page has the standard's default text, which the page's own thank-you text
  replaces.
- Reply-To is the core Email, and the admin's list and export show the core fields first.
- It can't go live without an address to send each message to, like any form page
  ([What stops a page going live](#what-stops-a-page-going-live)).

## News

Stories the charity publishes, with editor-managed categories and free tags (`news/models.py`):

- **The news page** lists stories newest first, ten per page, as cards, with a row of category
  filters ("All news" and each category).
- **Tag and category pages** (`/stories/tag/<tag>/`, `/stories/category/<slug>/`, under the
  news page's own address) show the same
  listing, filtered, with the filter in the heading.
- **A story** shows the news page's name and the date, the title, an introduction, a photo with
  its credit, the body, then its categories and tags as links to those pages.
- **The RSS feed** (`/stories/feed/`) has the latest 20 stories. A "Follow our news" box on the news
  page gives its address with a Copy link button, for readers who use a feed app.
- Categories are managed under **News categories** in the admin and translated with
  **Translate**. A slug is unique in each language, and a translation keeps it, so
  `/stories/category/field-updates/` and `/ne/stories/category/field-updates/` are the same
  category. A translated
  story keeps the original's categories and shows them in the language being read.

## Search

A search box in the header and a search page (`search/views.py`):

- Results are live, public pages **in the language being read**, ten per page. Each shows its
  title and its search description, else its summary, else its introduction.
- **Promoted results**: editors pin a page for a search term, per language; a promoted link to
  another website shows in both languages. Promotions show above the results.
- Every search is logged, so editors can see what people look for and promote answers.
- Search pages aren't indexed by search engines (robots.txt).

## SEO and sharing

So pages are found, and look right when shared:

- **Canonical link** and **Open Graph** tags on every page; a shared page shows its sharing image
  (set on the Promote tab, else the page's own photo) cropped to 1200×630, with a large Twitter
  card (`core/models.py`, `SocialMetaMixin`; `includes/social_meta.html`).
- **Sitemap** (`/sitemap.xml`): every live, public page in every language, with each page's
  translations as alternates ([Languages](languages.md)).
- **robots.txt** keeps search engines out of the admin and search, and links the sitemap.
- **Redirects**: editors add their own, and Wagtail adds one automatically when a page's slug
  changes, so old links keep working.

Every full URL (feed, sitemap, canonical, API) comes from the Wagtail Site record, which
`update_site_url` sets from `SITE_URL` ([Running the live site](../hosting.md)).

## URLs

| URL | |
|---|---|
| `/admin/` | The Wagtail admin |
| `/django-admin/` | Django's admin, for superusers only |
| `/en/…` or `/ne/…` | Pages and search in the site's second language ([Languages](languages.md#addresses)) |
| `/search/?query=…` | Search |
| `/donate/?appeal=<slug>&amount=<n>` | The Donate page with an appeal and amount preselected ([Appeals and giving](appeals-and-giving.md#donate-page)) |
| `/donate/thank-you/` | Where a sent pledge lands when the site has no way to pay; opening or reloading it saves nothing |
| `/donate/pay/<reference>/` | A pledge's pay page: the ways to pay, each on its own page under it ([Appeals and giving](appeals-and-giving.md#paying-a-pledge)) |
| `/donate/payment/<reference>/` | Where a payment provider sends the payer back: the site asks the provider, then goes to the pledge's online page (`…/go/` sends the payer back to the provider's page) |
| `/donate/gifts/<code>/` | A paid gift's page for friends, while its supporter agrees to show it ([Appeals and giving](appeals-and-giving.md#sharing-a-gift)) |
| `/stories/tag/…`, `/stories/category/…`, `/stories/feed/` | News listings and the RSS feed, under the news page's address |
| `/documents/<id>/<filename>` | Document downloads, through Wagtail's view, which checks a private collection's password or login |
| `/media/<path>` | Uploads, when Django serves them; never documents ([Security](../contributing/security.md)) |
| `/sitemap.xml`, `/robots.txt` | As above |
| `/api/v2/` | The API (below) |
| `/__debug__/` | django-debug-toolbar, in development only |

Everything else is a page in the [page tree](overview.md#the-page-tree). The admin, API,
documents, media, sitemap and robots.txt have no language prefix (`charity/urls.py`).

## The API

A read-only [Wagtail API v2](https://docs.wagtail.org/en/stable/advanced_topics/api/v2/usage.html)
of what editors publish, for a mobile app or a partner's website (`charity/api.py`):

| Endpoint | |
|---|---|
| `/api/v2/pages/` | Live, public pages in every language. Filter with `?type=campaigns.CampaignPage` or `?locale=ne`, and ask for fields with `?fields=*`. Each page's language is in `meta.locale` |
| `/api/v2/images/` | **Only images whose consent is confirmed**, because the endpoint hands out every image's original file, including ones never used on a page ([Images](images.md)) |
| `/api/v2/documents/` | Documents |

Appeals add `summary`, `hero_image` (an 800×450 rendition), `body`, `target_amount`,
`amount_raised`, `progress_percent`, `start_date`, `end_date`, `is_active` and
`donation_amounts` (each `amount` and `impact`). Stories add `date`, `introduction`, `hero_image`
(800×450), `body`, `tags` and `category_names`.

## Error pages

"Page not found" (404) uses the site's layout. The server error page (500) is a standalone
HTML page with no template tags, because it must render even when the database or a template
is what failed (`charity/templates/`).
