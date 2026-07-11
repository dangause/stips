export class ErrorSection {

    constructor() {
        this.errorSection = document.getElementById("error_section")
    }

    showErrorMessage(errorMessage) {
        this.errorSection.appendChild(new Text(errorMessage))
    }

    clearErrorMessages() {
        const messages = Array.from(this.errorSection.childNodes)
        for (const message of messages) {
            this.errorSection.removeChild(message)
        }
    }
}
