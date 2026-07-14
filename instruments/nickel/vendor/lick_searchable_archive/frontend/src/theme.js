import config from "./config.json"

const themeLink = document.getElementById("theme_link")
const themeButton = document.getElementById("theme_button")

themeButton.addEventListener("click", toggleTheme)
document.addEventListener("DOMContentLoaded", initializeTheme)

function setTheme(theme) {
    localStorage.setItem("theme", theme)
    if (theme == "dark") {
        themeLink.href="style/dark_theme.css"
        themeButton.textContent = "Switch to Light Theme"
    }
    else {
        themeLink.href="style/light_theme.css"
        themeButton.textContent = "Switch to Dark Theme"
    }
}

function initializeTheme(event) {
    let storedTheme = localStorage.getItem("theme")
    if (!storedTheme) {
        // Use the default theme from the HTML if it hasn't been set in local stoarge
        storedTheme = config.defaultTheme
    }
    setTheme(storedTheme)
}

function toggleTheme(event) {
    let storedTheme = localStorage.getItem("theme")
    if (!storedTheme) {
        // Use the default theme from the HTML if it hasn't been set in local stoarge
        storedTheme = config.defaultTheme
    }
    if (storedTheme == "dark") {
        setTheme("light")
    }
    else {
        setTheme("dark")
    }
}
