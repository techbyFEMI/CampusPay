import { getToken, API_BASE_URL } from './auth.js';
import { firestore } from './firebaseAuth.js';
import { collection, addDoc, doc, getDoc } from 'https://www.gstatic.com/firebasejs/12.15.0/firebase-firestore.js';


// ── State ─────────────────────────────────────────────────────────────────
let vendorId = null;
let editingProductId = null;
let deletingProductId = null;
let selectedAddImageFile = null;
let selectedEditImageFile = null;

// ── DOM refs ──────────────────────────────────────────────────────────────────
const productsList    = document.getElementById('products-list');
const productCountTag = document.getElementById('product-count-tag');
const addForm         = document.getElementById('add-product-form');
const addBtn          = document.getElementById('add-btn');
const formError       = document.getElementById('form-error');
const addImageInput   = document.getElementById('new-image');
const addImagePreview = document.getElementById('new-image-preview');

const editModal       = document.getElementById('edit-modal');
const closeEditBtn    = document.getElementById('close-edit-btn');
const editForm        = document.getElementById('edit-product-form');
const editName        = document.getElementById('edit-name');
const editPrice       = document.getElementById('edit-price');
const editDesc        = document.getElementById('edit-description');
const editImageInput  = document.getElementById('edit-image');
const editImagePreview= document.getElementById('edit-image-preview');
const saveBtn         = document.getElementById('save-btn');
const editError       = document.getElementById('edit-error');

const deleteModal     = document.getElementById('delete-modal');
const deleteNameLabel = document.getElementById('delete-product-name');
const cancelDeleteBtn = document.getElementById('cancel-delete-btn');
const confirmDeleteBtn= document.getElementById('confirm-delete-btn');

const toast           = document.getElementById('toast');

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  const token = await getToken();
  if (!token) {
    window.location.href = 'index.html';
    return;
  }

  const role = localStorage.getItem('role');
  if (role && role !== 'Vendor') {
    window.location.href = 'dashboard.html';
    return;
  }

  vendorId = localStorage.getItem('vendorId');
  if (!vendorId) {
    // Fallback: fetch vendorId from /auth/sync if not cached
    await refreshVendorId(token);
  }

  if (!vendorId) {
    showToast('Could not identify vendor. Please log in again.', 'error');
    setTimeout(() => window.location.href = 'index.html', 2000);
    return;
  }

  await loadProducts();

  // Add form submit
  addForm.addEventListener('submit', handleAddProduct);
  addImageInput?.addEventListener('change', handleAddImageSelect);

  // Edit modal
  closeEditBtn.addEventListener('click', closeEditModal);
  editModal.addEventListener('click', (e) => { if (e.target === editModal) closeEditModal(); });
  editForm.addEventListener('submit', handleSaveEdit);
  editImageInput?.addEventListener('change', handleEditImageSelect);

  // Delete modal
  cancelDeleteBtn.addEventListener('click', () => deleteModal.classList.remove('open'));
  deleteModal.addEventListener('click', (e) => { if (e.target === deleteModal) deleteModal.classList.remove('open'); });
  confirmDeleteBtn.addEventListener('click', handleConfirmDelete);
});

async function refreshVendorId(token) {
  try {
    const res = await fetch(`${API_BASE_URL}/auth/sync`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({ role: 'Vendor' }),
    });
    if (res.ok) {
      const data = await res.json();
      vendorId = data.user_id;
      localStorage.setItem('vendorId', vendorId);
      localStorage.setItem('role', data.role);
    }
  } catch (err) {
    console.error('Could not refresh vendor ID:', err);
  }
}

// ── Load Products ─────────────────────────────────────────────────────────────
async function loadProducts() {
  productsList.innerHTML = '<div class="loading-state">Loading products…</div>';
  const token = await getToken();

  try {
    const res = await fetch(`${API_BASE_URL}/api/catalog/vendors/${encodeURIComponent(vendorId)}`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });

    if (!res.ok) throw new Error('Failed to load products');

    const data = await res.json();
    const prods = data.products || [];
    renderProducts(prods);
  } catch (err) {
    console.error(err);
    productsList.innerHTML = '<div class="empty-state">Failed to load products. Please refresh.</div>';
  }
}

function renderProducts(prods) {
  productCountTag.textContent = `${prods.length} product${prods.length !== 1 ? 's' : ''}`;

  if (prods.length === 0) {
    productsList.innerHTML = '<div class="empty-state">No products yet. Add your first one above!</div>';
    return;
  }

  productsList.innerHTML = '';
  prods.forEach(p => productsList.appendChild(createProductRow(p)));
}

function formatMoney(val) {
  return '₦' + Number(val).toLocaleString('en-NG', { minimumFractionDigits: 2 });
}

function createProductRow(product) {
  const row = document.createElement('div');
  row.className = 'product-row';
  row.dataset.productId = product.product_id;

  const isAvail = product.is_available;

  const isFirestoreImage = typeof product.image_url === 'string' && product.image_url.startsWith('firestore://');
  const thumbnailHtml = product.image_url
    ? `<div class="product-thumb"><img ${isFirestoreImage ? `data-firestore-ref="${escAttr(product.image_url)}"` : `src="${escAttr(product.image_url)}"`} alt="${escAttr(product.name)}"></div>`
    : `<div class="product-thumb fallback">No Image</div>`;

  row.innerHTML = `
    ${thumbnailHtml}
    <div class="product-info">
      <div class="product-name">${escHtml(product.name)}</div>
      ${product.description ? `<div class="product-desc">${escHtml(product.description)}</div>` : ''}
    </div>
    <span class="product-price">${formatMoney(product.price)}</span>
    <label class="availability-toggle">
      <span>${isAvail ? 'Available' : 'Unavailable'}</span>
      <input class="availability-input" type="checkbox" aria-label="Allow purchases for ${escAttr(product.name)}" ${isAvail ? 'checked' : ''}>
      <span class="toggle-track"></span>
    </label>
    <div class="product-actions">
      <button class="action-icon-btn edit-btn" title="Edit" data-product-id="${escAttr(product.product_id)}">
        <i class="fa-solid fa-pen-to-square"></i>
      </button>
      <button class="action-icon-btn delete-btn" title="Delete" data-product-id="${escAttr(product.product_id)}" data-product-name="${escAttr(product.name)}">
        <i class="fa-solid fa-trash-can"></i>
      </button>
    </div>
  `;

  row.querySelector('.edit-btn').addEventListener('click', () => openEditModal(product));
  row.querySelector('.delete-btn').addEventListener('click', () => openDeleteModal(product));
  row.querySelector('.availability-input').addEventListener('change', (event) => {
    updateProductAvailability(product, event.currentTarget);
  });

  if (isFirestoreImage) {
    const imgEl = row.querySelector('img');
    if (imgEl) {
      loadFirestoreImage(product.image_url, imgEl).catch(err => {
        console.error('Failed to load Firestore image', err);
      });
    }
  }

  return row;
}

// ── Add Product ───────────────────────────────────────────────────────────────
async function handleAddProduct(e) {
  e.preventDefault();
  formError.classList.add('hidden');

  const name  = document.getElementById('new-name').value.trim();
  const price = parseFloat(document.getElementById('new-price').value);
  const desc  = document.getElementById('new-description').value.trim();

  if (!name) return showFormError(formError, 'Product name is required.');
  if (!price || price <= 0) return showFormError(formError, 'Price must be greater than zero.');

  addBtn.classList.add('btn-loading');
  const token = await getToken();

  try {
    let imageUrl = null;
    if (selectedAddImageFile) {
      imageUrl = await uploadProductImage(selectedAddImageFile);
    }

    const body = {
      name,
      price,
      description: desc || null,
    };
    if (imageUrl) body.image_url = imageUrl;

    const res = await fetch(`${API_BASE_URL}/api/catalog/products`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const err = await res.json();
      return showFormError(formError, err.detail || 'Failed to add product.');
    }

    addForm.reset();
    resetAddImageSelection();
    showToast('Product added!', 'success');
    await loadProducts();
  } catch (err) {
    console.error('Add product error', err);
    showFormError(formError, 'Network error. Please retry.');
  } finally {
    addBtn.classList.remove('btn-loading');
  }
}

// ── Edit Product ──────────────────────────────────────────────────────────────
function openEditModal(product) {
  editingProductId = product.product_id;
  editName.value = product.name;
  editPrice.value = product.price;
  editDesc.value = product.description || '';
  editError.classList.add('hidden');
  resetEditImageSelection();
  editModal.classList.add('open');
}

async function updateProductAvailability(product, input) {
  const nextAvailability = input.checked;
  input.disabled = true;
  const token = await getToken();

  try {
    const res = await fetch(`${API_BASE_URL}/api/catalog/products/${encodeURIComponent(product.product_id)}`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ is_available: nextAvailability }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Could not update product availability.');
    }

    product.is_available = nextAvailability;
    input.closest('.availability-toggle').querySelector('span').textContent =
      nextAvailability ? 'Available' : 'Unavailable';
    showToast(nextAvailability ? 'Students can now purchase this item.' : 'Purchases are paused for this item.', 'success');
  } catch (err) {
    console.error('Availability update error', err);
    input.checked = !nextAvailability;
    showToast(err.message || 'Could not update product availability.', 'error');
  } finally {
    input.disabled = false;
  }
}

function closeEditModal() {
  editModal.classList.remove('open');
  editingProductId = null;
  resetEditImageSelection();
}

function handleAddImageSelect() {
  const file = addImageInput.files?.[0];
  if (!file) {
    resetAddImageSelection();
    return;
  }

  const error = validateImageFile(file);
  if (error) {
    addImageInput.value = '';
    showFormError(formError, error);
    resetAddImageSelection();
    return;
  }

  formError.classList.add('hidden');
  selectedAddImageFile = file;
  showImagePreview(addImagePreview, file);
}

function handleEditImageSelect() {
  const file = editImageInput.files?.[0];
  if (!file) {
    resetEditImageSelection();
    return;
  }

  const error = validateImageFile(file);
  if (error) {
    editImageInput.value = '';
    showFormError(editError, error);
    resetEditImageSelection();
    return;
  }

  editError.classList.add('hidden');
  selectedEditImageFile = file;
  showImagePreview(editImagePreview, file);
}

function validateImageFile(file) {
  const allowed = ['image/jpeg', 'image/png', 'image/webp'];
  if (!allowed.includes(file.type)) {
    return 'Please choose a PNG, JPG, or WEBP image.';
  }
  if (file.size > 1 * 1024 * 1024) {
    return 'Image must be smaller than 1 MB when using Firestore.';
  }
  return null;
}

function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('Failed to read file'));
    reader.readAsDataURL(file);
  });
}

function showImagePreview(container, file) {
  container.innerHTML = `<img src="${escAttr(URL.createObjectURL(file))}" alt="Selected product image preview">`;
  container.classList.remove('hidden');
}

function resetAddImageSelection() {
  selectedAddImageFile = null;
  addImagePreview.innerHTML = '';
  addImagePreview.classList.add('hidden');
  addImageInput.value = '';
}

function resetEditImageSelection() {
  selectedEditImageFile = null;
  editImagePreview.innerHTML = '';
  editImagePreview.classList.add('hidden');
  editImageInput.value = '';
}

async function loadFirestoreImage(firestoreUrl, imgEl) {
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
}

async function uploadProductImage(file) {
  const dataUrl = await readFileAsDataURL(file);
  const matches = dataUrl.match(/^data:(.+);base64,(.+)$/);
  if (!matches) {
    throw new Error('Unable to parse selected image');
  }
  const contentType = matches[1];
  const base64 = matches[2];
  const ownerId = vendorId || localStorage.getItem('uid') || 'anonymous';
  const docRef = await addDoc(collection(firestore, 'product_images'), {
    ownerId,
    filename: file.name,
    contentType,
    base64,
    createdAt: new Date(),
  });

  return `firestore://product_images/${docRef.id}`;
}

async function handleSaveEdit(e) {
  e.preventDefault();
  editError.classList.add('hidden');

  const name  = editName.value.trim();
  const price = parseFloat(editPrice.value);
  const desc  = editDesc.value.trim();

  if (!name) return showFormError(editError, 'Product name is required.');
  if (!price || price <= 0) return showFormError(editError, 'Price must be greater than zero.');

  saveBtn.classList.add('btn-loading');
  const token = await getToken();

  try {
    const body = {
      name,
      price,
      description: desc || null,
    };

    if (selectedEditImageFile) {
      body.image_url = await uploadProductImage(selectedEditImageFile);
    }

    const res = await fetch(`${API_BASE_URL}/api/catalog/products/${encodeURIComponent(editingProductId)}`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const err = await res.json();
      return showFormError(editError, err.detail || 'Failed to update product.');
    }

    closeEditModal();
    showToast('Product updated!', 'success');
    await loadProducts();
  } catch (err) {
    console.error('Edit product error', err);
    showFormError(editError, 'Network error. Please retry.');
  } finally {
    saveBtn.classList.remove('btn-loading');
  }
}

// ── Delete Product ────────────────────────────────────────────────────────────
function openDeleteModal(product) {
  deletingProductId = product.product_id;
  deleteNameLabel.textContent = `"${product.name}"`;
  deleteModal.classList.add('open');
}

async function handleConfirmDelete() {
  if (!deletingProductId) return;
  confirmDeleteBtn.classList.add('btn-loading');
  const token = await getToken();

  try {
    const res = await fetch(`${API_BASE_URL}/api/catalog/products/${encodeURIComponent(deletingProductId)}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` },
    });

    if (!res.ok) {
      const err = await res.json();
      showToast(err.detail || 'Failed to delete product.', 'error');
      return;
    }

    deleteModal.classList.remove('open');
    deletingProductId = null;
    showToast('Product deleted.', '');
    await loadProducts();
  } catch (err) {
    showToast('Network error. Please retry.', 'error');
  } finally {
    confirmDeleteBtn.classList.remove('btn-loading');
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function showFormError(el, msg) {
  el.textContent = msg;
  el.classList.remove('hidden');
}

let toastTimer = null;
function showToast(msg, type = '') {
  toast.textContent = msg;
  toast.className = `toast show ${type ? type + '-toast' : ''}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.className = 'toast hidden'; }, 3500);
}

function escHtml(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function escAttr(str) {
  return String(str || '').replace(/"/g,'&quot;');
}
