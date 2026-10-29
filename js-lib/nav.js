import { wireHamburger } from "./uiUtils.js";
import { auth } from "/js/auth.js";

const userLinks = `
  <li><a href="/fbp-home.html">FBP Home</a></li>
  <li><a href="/userprofile.html">Update My Profile</a></li>
  <li><a href="/getpicksheet.html" title="Picks can be made between Tuesday Noon EST and Thursday 8:00PM EST">Make My Picks For The Week</a></li>
  <li><a href="/showweeklyresults.html" title="Results are available Tuesday Noon EST">Show Results For The Previous Week</a></li>
  <li><a href="/viewstandings.html" title="Current Standings Might Not Include the Current Week">View Current Standings</a></li>
  <li><a href="/getgridsheet.html" title="Available after the Pool closes at 8:00PM EST on Thursday">Get Grid Sheet For The Week</a></li>
  <li><a href="/getteamrecords.html" title="View NFL Team Records Against the Spread">View NFL Team Records Against the Spread</a></li>
  <li><a href="/faq.html">FBP FAQ</a></li>
  <li><a href="/signout.html">Sign out</a></li>
`;

const adminLinks = `
  <li><a href="/fbp-admin/admin.html">Admin Home</a></li>
`;

export async function initNav() {
  const isAdmin = await auth.isAdmin();
  const allLinks = userLinks + (isAdmin ? adminLinks : "");

  // Inject mobile nav into header
  const header = document.querySelector("header");
  if (header) {
    const btn = document.createElement("button");
    btn.id = "menuBtn";
    btn.className = "menu-btn";
    btn.setAttribute("aria-controls", "main-nav");
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-label", "Toggle menu");
    btn.innerHTML = '<span></span><span></span><span></span>';
    header.appendChild(btn);

    const nav = document.createElement("nav");
    nav.id = "main-nav";
    nav.setAttribute("aria-label", "Main navigation");
    nav.setAttribute("data-open", "false");
    nav.innerHTML = `<ul>${allLinks}</ul>`;
    header.appendChild(nav);
  }

  // Inject desktop nav into aside
  const aside = document.querySelector("aside.nav-choices");
  if (aside) {
    aside.innerHTML = `
      <nav aria-label="Main navigation">
        <ul>${allLinks}</ul>
      </nav>
    `;
  }

  // Wire hamburger after nav exists in DOM
  wireHamburger({
    buttonId: "menuBtn",
    navId: "main-nav",
    openText: "✕ Menu",
    closedText: "☰ Menu",
    closeOnLinkClick: true,
  });
}
