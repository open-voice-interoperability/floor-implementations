#include <iostream>
#include <string>
#include <curl/curl.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

class HttpsClient {
private:
    CURL* curl;
    std::string response_data;
    
    // Callback function to handle response data
    static size_t WriteCallback(void* contents, size_t size, size_t nmemb, void* userp) {
        ((std::string*)userp)->append((char*)contents, size * nmemb);
        return size * nmemb;
    }

public:
    HttpsClient() {
        curl_global_init(CURL_GLOBAL_DEFAULT);
        curl = curl_easy_init();
    }
    
    ~HttpsClient() {
        if (curl) {
            curl_easy_cleanup(curl);
        }
        curl_global_cleanup();
    }
    
    // Make an HTTPS POST request with JSON input and output
    json post(const std::string& url, const json& input_json) {
        json result;
        
        if (!curl) {
            result["error"] = "Failed to initialize CURL";
            return result;
        }
        
        response_data.clear();
        
        // Convert JSON to string
        std::string json_str = input_json.dump();
        
        // Set up headers
        struct curl_slist* headers = nullptr;
        headers = curl_slist_append(headers, "Content-Type: application/json");
        headers = curl_slist_append(headers, "Accept: application/json");
        
        // Configure CURL
        curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(curl, CURLOPT_POST, 1L);
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json_str.c_str());
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response_data);
        
        // Enable SSL/TLS
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
        
        // Perform the request
        CURLcode res = curl_easy_perform(curl);
        
        // Clean up headers
        curl_slist_free_all(headers);
        
        // Check for errors
        if (res != CURLE_OK) {
            result["error"] = curl_easy_strerror(res);
            return result;
        }
        
        // Get HTTP response code
        long http_code = 0;
        curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
        
        // Parse response JSON
        try {
            result = json::parse(response_data);
            result["http_code"] = http_code;
        } catch (const json::parse_error& e) {
            result["error"] = "Failed to parse JSON response";
            result["parse_error"] = e.what();
            result["raw_response"] = response_data;
            result["http_code"] = http_code;
        }
        
        return result;
    }
    
    // Set custom timeout (in seconds)
    void setTimeout(long seconds) {
        if (curl) {
            curl_easy_setopt(curl, CURLOPT_TIMEOUT, seconds);
        }
    }
    
    // Set custom headers
    void setHeader(const std::string& header) {
        // This would require storing headers as a member variable
        // For simplicity, headers are set in the post() method
    }
};

// Example usage
int main() {
    HttpsClient client;
    
    // Set timeout to 30 seconds
    client.setTimeout(30);
    
    // Prepare JSON input
    json input;
    input["key"] = "value";
    input["number"] = 42;
    input["array"] = json::array({1, 2, 3});
    
    std::cout << "Sending request..." << std::endl;
    std::cout << "Input JSON: " << input.dump(2) << std::endl;
    
    // Make POST request (replace with your actual API endpoint)
    json response = client.post("https://httpbin.org/post", input);
    
    // Display response
    std::cout << "\nResponse:" << std::endl;
    std::cout << response.dump(2) << std::endl;
    
    return 0;
}
