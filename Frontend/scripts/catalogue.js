// existing placeholder

import { getToken, API_BASE_URL} from './auth.js';
import { firestore } from './firebaseAuth.js';
import { doc, getDoc } from 'https://www.gstatic.com/firebasejs/12.15.0/firebase-firestore.js';

async function loadFirestoreImage(firestoreUrl, imgEl) {
	try {
		const [collectionName, docId] = firestoreUrl.replace('firestore://', '').split('/');
		if (!collectionName || !docId) {
			throw new Error('Invalid Firestore image URL');
		}
		const docRef = doc(firestore, collectionName, docId);
		const snapshot = await getDoc(docRef);
		if (!snapshot.exists()) {
			throw new Error('Firestore image document does not exist');
		}
		const data = snapshot.data();
		if (!data || !data.contentType || !data.base64) {
			throw new Error('Invalid Firestore image document');
		}
		imgEl.src = `data:${data.contentType};base64,${data.base64}`;
	} catch (err) {
		console.error('Failed to load Firestore image:', err);
	}
}

function qS(param) {
	const url = new URL(window.location.href);
	return url.searchParams.get(param);
}

function currency(n) {
	return new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format(n);
}

function saveCheckoutItem(product, vendor) {
	const payload = {
		vendor_id: vendor.vendor_id,
		vendor_name: vendor.name,
		name: product.name,
		description: product.description || 'Purchase from ' + vendor.name,
		price: Number(product.price || 0),
	};
	window.sessionStorage.setItem('checkoutItem', JSON.stringify(payload));
	window.location.href = 'purchase.html';
}

function createProductCard(product, vendor) {
	const article = document.createElement('article');
	article.className = 'product-card';

	const imgWrap = document.createElement('div');
	imgWrap.className = 'card-image_container card-image-container';
	const img = document.createElement('img');
	img.alt = product.name;

	const isFirestoreImage = typeof product.image_url === 'string' && product.image_url.startsWith('firestore://');
	if (isFirestoreImage) {
		img.src = 'assets/product-placeholder.jpg';
		loadFirestoreImage(product.image_url, img);
	} else if (product.image_url) {
		img.src = product.image_url;
	} else {
		img.src = vendor.cover_image_url || 'assets/product-placeholder.jpg';
	}
	imgWrap.appendChild(img);

	const content = document.createElement('div');
	content.className = 'card-content';
	const title = document.createElement('h2');
	title.className = 'product-title';
	title.textContent = product.name;
	content.appendChild(title);

	const desc = document.createElement('p');
	desc.className = 'product-desc';
	desc.textContent = product.description || '';
	content.appendChild(desc);

	const loc = document.createElement('div');
	loc.className = 'product-location';
	loc.innerHTML = `<i class="fa-solid fa-location-dot"></i> ${vendor.location}`;
	content.appendChild(loc);

	const price = document.createElement('div');
	price.className = 'product-price';
	price.textContent = currency(product.price || 0);
	content.appendChild(price);

	const btn = document.createElement('button');
	btn.className = 'btn-purchase';
	btn.type = 'button';
	btn.textContent = product.is_available ? 'Purchase' : 'Unavailable';
	btn.disabled = !product.is_available;
	btn.addEventListener('click', () => {
		saveCheckoutItem(product, vendor);
	});
	content.appendChild(btn);

	article.appendChild(imgWrap);
	article.appendChild(content);
	return article;
}

function renderVendorHeader(vendor) {
	const header = document.getElementById('vendor-header');
	header.innerHTML = '';
	const wrap = document.createElement('div');
	wrap.className = 'vendor-header-card';

	const img = document.createElement('img');
	img.src = vendor.cover_image_url || 'assets/vendor-placeholder.jpg';
	img.alt = vendor.name;
	img.className = 'vendor-cover';
	wrap.appendChild(img);

	const info = document.createElement('div');
	info.className = 'vendor-info';
	info.innerHTML = `<h2>${vendor.name}</h2>
	<div class="meta-info"><i class="fa-solid fa-location-dot"></i> ${vendor.location}</div>
	<div class="meta-info"><i class="fa-solid fa-phone"></i> ${vendor.phone}</div>`;

	wrap.appendChild(info);
	header.appendChild(wrap);
}

document.addEventListener('DOMContentLoaded', async () => {
	const vendorId = qS('vendor_id');
	const grid = document.getElementById('product-grid');

	if (!vendorId) {
		grid.innerHTML = '<div class="loading-placeholder">No vendor selected. Open a vendor from the Vendor Directory.</div>';
		return;
	}

	const token = await getToken();
	if (!token) {
		window.location.href = 'index.html';
		return;
	}

	try {
		grid.innerHTML = '<div class="loading-placeholder">Loading catalogue&hellip;</div>';
		const res = await fetch(`${API_BASE_URL}/api/catalog/vendors/${encodeURIComponent(vendorId)}`, {
			headers: { 'Authorization': `Bearer ${token}` }
		});
		if (res.status === 401) {
			window.location.href = 'index.html';
			return;
		}
		if (!res.ok) throw new Error('Failed to load catalogue');
		const vendor = await res.json();

		renderVendorHeader(vendor);

		grid.innerHTML = '';
		if (!vendor.products || vendor.products.length === 0) {
			grid.innerHTML = '<div class="loading-placeholder">No products available</div>';
			return;
		}

		vendor.products.forEach(p => grid.appendChild(createProductCard(p, vendor)));

		// client-side search
		const searchInput = document.querySelector('.search-box input');
		if (searchInput) {
			searchInput.addEventListener('input', (e) => {
				const q = e.target.value.toLowerCase().trim();
				const cards = grid.querySelectorAll('.product-card');
				cards.forEach(card => {
					const text = card.textContent.toLowerCase();
					card.style.display = text.includes(q) ? '' : 'none';
				});
			});
		}

	} catch (err) {
		console.error(err);
		grid.innerHTML = '<div class="loading-placeholder">Failed to load catalogue</div>';
	}
});
