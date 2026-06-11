document.addEventListener("DOMContentLoaded", () => {
    const savedTheme = localStorage.getItem("spkb_theme") || "dark";
    if (savedTheme === "light") {
        document.documentElement.setAttribute("data-theme", "light");
    } else {
        document.documentElement.removeAttribute("data-theme");
    }
    updateThemeIcon(savedTheme);
});

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
    const newTheme = currentTheme === "dark" ? "light" : "dark";
    
    if (newTheme === "light") {
        document.documentElement.setAttribute("data-theme", "light");
    } else {
        document.documentElement.removeAttribute("data-theme");
    }
    
    localStorage.setItem("spkb_theme", newTheme);
    updateThemeIcon(newTheme);
}

function updateThemeIcon(theme) {
    // Icon toggling is now handled purely by CSS using [data-theme="light"]
}
