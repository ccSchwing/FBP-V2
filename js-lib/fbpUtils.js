import { getServiceUrl } from "/js-lib/urlConfig.js";
export async function getCurrentWeek() {
    const { getServiceUrl } = await import("/js-lib/urlConfig.js");
    const urlKey = "getCurrentWeek";
    const serviceUrl = await getServiceUrl(urlKey);
    const response = await fetch(serviceUrl, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
    });
    if (!response.ok) {
        throw new Error(`Failed to fetch current week data with status ${response.status}`);
    }
    const data = await response.json();
    if (!data) {
        throw new Error("Received empty data for current week.");
    }
    console.log("Fetched current week data:", data);
    return data;
}

 async function getPoolStatus() {
        try {
          const { getServiceUrl } = await import("/js-lib/urlConfig.js");
          const urlKey = "getPoolStatus";
          const serviceUrl = await getServiceUrl(urlKey);
          const response = await fetch(serviceUrl, {
            method: "GET",
            headers: {
              "Content-Type": "application/json",
            },
          });
          if (!response.ok) {
            throw new Error(
              alert("We could not determine the pool status. Please contact the pool administrator at fbpadmin@my-fbp.com"),
              `Failed to fetch pool status with status ${response.status}`,
            );
          } else {
            const data = await response.json();
            console.log("Fetched pool status:", data);
            if ( ! data?.pool_open) {
              alert("FBP Pool is currently closed.  You can view the pick sheet, but you cannot make or change picks at this time.");
              return data.pool_open;
            } else {
              return data.pool_open;
            }
          }
        } catch (error) {
          console.error("Error fetching pool status:", error);
          alert(
            "We could not determine the pool status.  Please contact the pool administrator at fbpadmin@my-fbp.com",
          );
        }
      }
