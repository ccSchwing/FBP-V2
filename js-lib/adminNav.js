import { wireHamburger } from "./uiUtils.js";
import { auth } from "/js/auth.js";

const adminLinks = `
  <li><a href="/fbp-home.html">FBP Home</a></li>
  <li><a href="/fbp-admin/signup.html">Create FBP Account</a></li>
  <li><a href="/fbp-admin/manageuserprofiles.html">Manage User Profiles</a></li>
  <li><a href="/fbp-admin/dashboard.html">Admin Dashboard</a></li>
  <li><a href="/fbp-admin/getpicksheet.html">Create Picksheet PDF</a></li>
  <li><a href="/fbp-admin/getgridsheet.html">Create Gridsheet PDF</a></li>
`;

export async function initAdminNav() {
  const isAdmin = await auth.isAdmin();
  if (!isAdmin) {
    const { getServiceUrl } = await import("./urlConfig.js");
    location.href = await getServiceUrl("homePage");
    return;
  }

  // Inject mobile nav into header
  const header = document.querySelector("header");
  if (header) {
    const btn = document.createElement("button");
    btn.id = "menuBtn";
    btn.className = "menu-btn";
    btn.setAttribute("aria-controls", "main-nav");
    btn.setAttribute("aria-expanded", "false");
    btn.innerHTML = '<span></span><span></span><span></span>';
    header.appendChild(btn);

    const nav = document.createElement("nav");
    nav.id = "main-nav";
    nav.setAttribute("aria-label", "Main navigation");
    nav.setAttribute("data-open", "false");
    nav.innerHTML = `<ul>${adminLinks}</ul>`;
    header.appendChild(nav);
  }

  // Inject desktop nav into aside
  const aside = document.querySelector("aside.nav-choices");
  if (aside) {
    aside.innerHTML = `
      <nav aria-label="Main navigation">
        <ul>${adminLinks}</ul>
      </nav>
    `;
  }

  wireHamburger({
    buttonId: "menuBtn",
    navId: "main-nav",
    closeOnLinkClick: true,
  });
}
