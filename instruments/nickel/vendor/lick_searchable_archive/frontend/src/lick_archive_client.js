export class LickArchiveClient {
    loginUser = null
    apiCSRFToken = null
    errorMessage = null
    urlBase = null

    constructor(apiURLBase) {
        this.urlBase = apiURLBase
    }

    async getLoginStatus() {
        try {
            const response = await fetch(this.urlBase + "api/login")
            if (!response.ok) {
                this.loginUser = null
                this.apiCSRFToken = null
                this.errorMessage = `Received status ${response.status} from archive when checking login status.`
            }
            else {
                const loginStatus = await response.json()
                if (loginStatus.logged_in) {
                    this.loginUser = loginStatus.user
                    this.apiCSRFToken = loginStatus.csrfmiddlewaretoken
                    this.errorMessage = null
                }
                else {
                    this.loginUser = null
                    this.apiCSRFToken = loginStatus.csrfmiddlewaretoken
                    this.errorMessage = null
                }
            }
        }
        catch (error) {
            this.loginUser = null
            this.apiCSRFToken = null
            this.errorMessage = error.message
        }
    }

    async login(username, password) {
        try {
            if (this.apiCSRFToken == null) {
                await this.getLoginStatus()
                if (this.errorMessage != null) {
                    throw new Error(this.errorMessage)
                }
            }
            const postBody = new FormData()
            postBody.append("csrfmiddlewaretoken", this.apiCSRFToken)
            postBody.append("username", username)
            postBody.append("password", password)
            const response = await fetch(this.urlBase + "api/login", {
                method: "POST",
                body: postBody
            })
            if (!response.ok) {
                if (response.status == 403) {
                    // Password was rejected, don't show the status code
                    this.errorMessage = "Login failed"
                }
                else {
                    this.errorMessage = `Login failed, status code ${response.status}`
                }
                this.loginUser = null
                this.apiCSRFToken = null
            }
            else {
                const responseJson = await response.json()
                this.errorMessage = null
                this.loginUser = responseJson.user
                this.apiCSRFToken = responseJson.csrfmiddlewaretoken
            }
        }
        catch(error) {
            this.errorMessage = error.message
            this.apiCSRFToken = null
        }

    }
    async logout() {
        try {
            if (this.apiCSRFToken == null) {
                await this.getLoginStatus()
                if (this.errorMessage != null) {
                    throw new Error(this.errorMessage)
                }
            }
            const postBody = new FormData()
            postBody.append("csrfmiddlewaretoken", this.apiCSRFToken)
            const response = await fetch(this.urlBase + "api/logout", {
                method: "POST",
                body: postBody
            })
            if (!response.ok) {
                this.errorMessage = `Failed to logout, status code ${response.status}`
                this.apiCSRFToken = null
            }
            else {
                const responseJson = await response.json()
                this.errorMessage = null
                this.loginUser = null
                this.apiCSRFToken = null
            }
        }
        catch(error) {
            this.errorMessage = error.message
            this.apiCSRFToken = null
        }
    }

    async get_token() {
        try {
            if (this.apiCSRFToken == null) {
                const response = await fetch(this.urlBase + "api/get_csrf_token")
                if (!response.ok) {
                    this.apiCSRFToken = null
                    this.errorMessage = `Received status ${response.status} from archive.`
                }
                else {
                    this.apiCSRFToken = await response.json().csrfmiddlewaretoken
                    this.errorMessage = null
                }
            }
        }
        catch(error) {
            this.apiCSRFToken = null
            this.errorMessage = error.message
        }
    }

    async runQuery(queryURL) {

        let results = {"count": 0, "previous": null, "next": null, "results": null, "error": 'Failed to run query.'}
        try {
            const response = await fetch(queryURL)

            if(!response.ok) {
                results["error"] = `Archive server returned error code ${response.status}`
            }
            else {
                results = await response.json()
            }
        }
        catch(error) {
            results["error"] = `Failed to contact archive server: ${error}`
        }
        return results
    }
}
