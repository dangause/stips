
//////////////// Header Login/Logout Controls /////////////////////



export class LoginControls {

    constructor(archiveClient, errorSection) {
        this.archiveClient = archiveClient
        this.errorSection = errorSection

        this.userSection = document.getElementById("user_section")
        this.loginoutButton = document.getElementById("loginout_button")
        this.userName = document.getElementById("user_name")

        document.addEventListener("DOMContentLoaded", this.setLoginStatus.bind(this))
        this.loginoutButton.addEventListener("click", this.loginoutUser.bind(this))
    }

    async setLoginStatus(event) {
        await this.archiveClient.getLoginStatus()

        if (this.archiveClient.errorMessage != null) {
            var loginStatus = "Failed to get login status."
            this.userName.hidden = true
            this.loginoutButton.name = "login"
            this.loginoutButton.textContent = "Login"
            this.errorSection.showErrorMessage(archiveClient.errorMessage)
        }
        else if (this.archiveClient.loginUser != null) {
            var loginStatus = `You are logged in as `
            this.userName.hidden = false
            this.loginoutButton.name = "logout"
            this.loginoutButton.textContent = "Logout"
            this.errorSection.clearErrorMessages()
        }
        else {
            var loginStatus = "You are not logged in."
            this.userName.hidden = true
            this.loginoutButton.name = "login"
            this.loginoutButton.textContent = "Login"
            this.errorSection.clearErrorMessages()
        }
        this.userSection.replaceChild(new Text(loginStatus),this.userSection.firstChild)
        if (!this.userName.hidden) {
            this.userName.textContent = this.archiveClient.loginUser
        }
    }

    async loginoutUser(event) {
        if (event.target.name == "login"){
            // Go to the login link
            window.location.href = "login.html"
        }
        else {
            // Otherwise logout
            await this.archiveClient.logout()
            await this.setLoginStatus()
        }
    }
}
