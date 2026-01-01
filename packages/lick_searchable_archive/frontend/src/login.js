import config from "./config.json"
import {LoginControls} from "./login_controls.js"
import {LickArchiveClient} from "./lick_archive_client.js"
import {ErrorSection} from "./error_section.js"
import "./theme.js"

const errorSection = new ErrorSection()
const archiveClient = new LickArchiveClient(config.backendURLBase)
const loginControls = new LoginControls(archiveClient, errorSection)

const loginText = document.getElementById("login_text")
const loginUsername = document.getElementById("login_username")
const loginPassword = document.getElementById("login_password")
const loginButton = document.getElementById("login_button")

loginButton.addEventListener("click", login)
loginUsername.addEventListener("keydown", loginOnEnter)
loginPassword.addEventListener("keydown", loginOnEnter)

async function loginOnEnter(event) {
    if (event.key == "Enter") {
        login()
    }
}

async function login(event) {
    await archiveClient.login(loginUsername.value,loginPassword.value)
    if (archiveClient.errorMessage != null)
    {
        loginText.textContent = archiveClient.errorMessage
        loginText.className = "login_error"
    }
    else if (archiveClient.loginUser == null) {
        loginText.textContent = "Login failed"
        loginText.className = "login_error"
    }
    else {
        // Login successful, return to main page
        window.location.href = "index.html"
    }
}
