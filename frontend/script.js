// Get references to static elements
const fileInput = document.getElementById('file-input');
const menuImg = document.getElementById('menu-img');
const drinksTable = document.getElementById('drinks-table');
const uploadArea = document.getElementById('upload-area');
const fileInfo = document.getElementById('file-info');

// Drag and drop functionality
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    uploadArea.addEventListener(eventName, preventDefaults, false);
});
function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}
['dragenter', 'dragover'].forEach(eventName => {
    uploadArea.addEventListener(eventName, highlight, false);
});
['dragleave', 'drop'].forEach(eventName => {
    uploadArea.addEventListener(eventName, unhighlight, false);
});
function highlight() {
    uploadArea.classList.add('dragover');
}
function unhighlight() {
    uploadArea.classList.remove('dragover');
}
uploadArea.addEventListener('drop', handleDrop, false);
function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length) {
        fileInput.files = files;
        const event = new Event('change');
        fileInput.dispatchEvent(event);
    }
}
uploadArea.addEventListener('click', () => {
    fileInput.click();
});

// Prevent double file dialog when clicking file input
fileInput.addEventListener('click', (e) => {
    e.stopPropagation();
});

// File input change handler
fileInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Update file info
    fileInfo.textContent = `Selected file: ${file.name}`;

    // Show image
    const reader = new FileReader();
    reader.onload = (ev) => {
        menuImg.src = ev.target.result;
        menuImg.style.display = 'block';
        // Keep the upload area visible but make it less prominent
        uploadArea.style.opacity = '0.7';
    };
    reader.readAsDataURL(file);

    // Show loading state (simple overlay)
    showLoading(true);
    drinksTable.innerHTML = '';

    // Send to backend
    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('http://localhost:8000/upload/', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();

        if (data.error) {
            drinksTable.innerHTML = `<tr><td colspan="6">Error: ${data.error}</td></tr>`;
            showLoading(false);
            return;
        }

        // Build table
        drinksTable.innerHTML = '';
        if (data.drinks && data.drinks.length) {
            const headers = Object.keys(data.drinks[0]);
            const thead = document.createElement('thead');
            const headerRow = document.createElement('tr');
            headers.forEach(h => {
                const th = document.createElement('th');
                th.textContent = h.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                headerRow.appendChild(th);
            });
            thead.appendChild(headerRow);
            drinksTable.appendChild(thead);
            const tbody = document.createElement('tbody');
            data.drinks.forEach(row => {
                const tr = document.createElement('tr');
                headers.forEach(h => {
                    const td = document.createElement('td');
                    td.textContent = row[h] ?? 'N/A';
                    tr.appendChild(td);
                });
                tbody.appendChild(tr);
            });
            drinksTable.appendChild(tbody);
        } else {
            drinksTable.innerHTML = '<tr><td colspan="6">No drinks found</td></tr>';
        }
    } catch (error) {
        drinksTable.innerHTML = `<tr><td colspan="6">Error: ${error.message}</td></tr>`;
    } finally {
        showLoading(false);
        // Reset upload area opacity
        uploadArea.style.opacity = '1';
    }
});

// Simple loading overlay
function showLoading(show) {
    let loading = document.getElementById('loading-spinner');
    if (!loading) {
        loading = document.createElement('div');
        loading.className = 'loading-spinner';
        loading.id = 'loading-spinner';
        loading.innerHTML = `
            <div class="spinner"></div>
            <p>Analyzing menu...</p>
        `;
        document.body.appendChild(loading);
    }
    loading.style.display = show ? 'flex' : 'none';
}