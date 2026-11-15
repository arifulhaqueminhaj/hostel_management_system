// Nestora HMS - Main JavaScript

// Sidebar toggle
function toggleSidebar() {
    document.querySelector('.sidebar').classList.toggle('collapsed');
    document.querySelector('.main-content').classList.toggle('full');
}

// Auto-dismiss alerts
document.addEventListener('DOMContentLoaded', function() {
    // Auto dismiss alerts after 5 seconds
    setTimeout(function() {
        document.querySelectorAll('.alert-dismissible').forEach(function(el) {
            var bsAlert = new bootstrap.Alert(el);
            bsAlert.close();
        });
    }, 5000);
});

// Confirm delete
function confirmDelete(message) {
    return confirm(message || 'Are you sure you want to delete this item?');
}

// Format currency
function formatCurrency(amount) {
    return '\u09f3 ' + parseFloat(amount).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Toggle sidebar on mobile
document.addEventListener('DOMContentLoaded', function() {
    var sidebarToggle = document.getElementById('sidebarToggle');
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function() {
            document.querySelector('.sidebar').classList.toggle('show');
        });
    }
});
