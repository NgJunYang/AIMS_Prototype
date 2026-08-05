"use strict";

/* Where the AIMS API lives.
 *
 * "" (default) means same-origin: the FastAPI app is serving this file
 * itself, so /api/... resolves against the page's own host. This is the
 * right setting whenever app.py serves static/ directly (local dev, or a
 * single deployment on Render/Railway/etc).
 *
 * If this frontend is instead published on its own (e.g. GitHub Pages),
 * there is no backend at that origin - set this to the URL of the
 * separately-deployed backend, e.g.:
 *   window.AIMS_API_BASE = "https://aims-backend.onrender.com";
 */
window.AIMS_API_BASE = "";
