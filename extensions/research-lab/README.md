# JobDetector Research Lab (experimental)

1. Unzip this folder. Open chrome://extensions in Chrome.
2. Enable Developer mode, choose Load unpacked, and select this folder.
3. Sign in to JobDetector with an active Plus/trial or Tuxy VIP account.
4. Open a LinkedIn search/feed page, expand the desired post, and click this extension's toolbar icon once to enable research buttons on the current tab.
5. Click Research this job on the chosen post. The report opens in JobDetector.

No post permalink or JobDetector job-database record is required. Only the selected post's visible text, professional author heading, public links and source page URL are transferred after clicking Research. The payload uses a URL fragment, not a query string. No LinkedIn cookies, password, browsing history or other posts are sent. No network host permission or automatic background crawling is requested. Uninstall or reload the LinkedIn tab to remove the injected buttons.

LinkedIn's DOM changes. Some post layouts may not receive a button; copy the expanded post text into the lab as a fallback. This prototype has not been published to the Chrome Web Store.
