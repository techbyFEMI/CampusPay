import { getToken, API_BASE_URL } from "./auth.js";


function createVendorCard(vendor) {
  const article = document.createElement('article');
  article.className = 'vendor-card';

  const imageContainer = document.createElement('div');
  imageContainer.className = 'card-image-container';
  const img = document.createElement('img');
  img.src = vendor.cover_image_url || 'assets/vendor-placeholder.jpg';
  img.alt = `${vendor.name} cover`;
  imageContainer.appendChild(img);

  const content = document.createElement('div');
  content.className = 'card-content';
  const h2 = document.createElement('h2');
  h2.textContent = vendor.name;
  content.appendChild(h2);

  const metaLoc = document.createElement('div');
  metaLoc.className = 'meta-info';
  metaLoc.innerHTML = `<i class="fa-solid fa-location-dot"></i> ${vendor.location}`;
  content.appendChild(metaLoc);

  const metaPhone = document.createElement('div');
  metaPhone.className = 'meta-info';
  metaPhone.innerHTML = `<i class="fa-solid fa-phone"></i> ${vendor.phone}`;
  content.appendChild(metaPhone);

  const btn = document.createElement('button');
  btn.className = 'action-btn';
  btn.type = 'button';
  btn.textContent = 'View Catalog';
  btn.setAttribute('data-vendor-id', vendor.vendor_id);
  btn.addEventListener('click', () => {
    // navigate to catalogue with vendor_id (relative path)
    const qs = `?vendor_id=${encodeURIComponent(vendor.vendor_id)}`;
    window.location.href = `catalogue.html${qs}`;
  });

  content.appendChild(btn);

  article.appendChild(imageContainer);
  article.appendChild(content);
  return article;
}

document.addEventListener('DOMContentLoaded', async () => {
  const container = document.getElementById('vendor-list');
  container.innerHTML = '<div class="loading-placeholder">Loading vendors&hellip;</div>';

  const token = await getToken();
  if (!token) {
    console.log('No authenticated token, redirecting to index.html...');
    window.location.href = 'index.html';
    return;
  }

  try {
    const res = await fetch(`${API_BASE_URL}/api/catalog/vendors`, {
      headers: { 
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json' }
    });

    if (res.status === 401) {
      window.location.href = 'index.html';
      return;
    }

    if (!res.ok) throw new Error('Failed to load vendors');

    const vendors = await res.json();
    container.innerHTML = '';

    if (!Array.isArray(vendors) || vendors.length === 0) {
      container.innerHTML = '<div class="loading-placeholder">No vendors found</div>';
      return;
    }

    vendors.forEach(v => container.appendChild(createVendorCard(v)));

    // client-side search
    const searchInput = document.querySelector('.search-box input');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        const q = e.target.value.toLowerCase().trim();
        const cards = container.querySelectorAll('.vendor-card');
        cards.forEach(card => {
          const text = card.textContent.toLowerCase();
          card.style.display = text.includes(q) ? '' : 'none';
        });
      });
    }

  } catch (err) {
    console.error(err);
    container.innerHTML = '<div class="loading-placeholder">Failed to load vendors</div>';
  }
});
