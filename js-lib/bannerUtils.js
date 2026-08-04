export async function setBannerStatusMessage() {
      const { getServiceUrl } = await import("/js-lib/urlConfig.js");
      const statusURL = await getServiceUrl("getPoolStatus");
      try {
        const response = await fetch(statusURL, {
          method: "GET",
          headers: { "Content-Type": "application/json" },
        });
        if (response.ok) {
          const data = await response.json();
          console.log("Pool Status Response:", data);
          const statusBanner = document.getElementById("statusBanner");
          if (!statusBanner) {
            return;
          }
          const poolData = JSON.parse(data.body);
          console.log("Pool status: " + poolData.pool_open);
          if (poolData.pool_open === true) {
            const message = "FBP Pool is OPEN for picks. Grid Sheet Weekly results cannot be shown until the pool is closed. Hover over the links below for additional info.";
            statusBanner.textContent = message;
            statusBanner.style.display = "block";
          } else {
            const message = "FBP Pool is currently CLOSED. Weekly results and current standings are available for viewing. Hover over the links below for additional info.";
            statusBanner.textContent = message;
            statusBanner.style.display = "block";
          }
        } else {
          const statusBanner = document.getElementById("statusBanner");
          if (statusBanner) {
            const message = "Unable to determine pool status. Contact support at fbpadmin@my-fbp.com.";
            statusBanner.textContent = message;
            statusBanner.style.display = "block";
          }
        }
      } catch (error) {
        console.error("Error fetching pool status:", error);
      }
    }
