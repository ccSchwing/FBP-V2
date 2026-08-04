    export async function getUserStatus() {
      try {
        const { getServiceUrl } = await import("/js-lib/urlConfig.js");
        const apiEndpoint = await getServiceUrl("getUserStatus");
        const options = {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({ email: window.user.profile.email })
        };
        const response = await fetch(apiEndpoint, options);
        if (!response.ok) {
          console.error("Network response was not ok:", response.statusText);
          alert("Unable to fetch user status right now. Contact fbpadmin@my-fbp.com if you think this is an error.");
          throw new Error("Network response was not ok");
        }
        const userData = await response.json();
        console.log("userData:", userData);
        if (userData.isAccountLocked) {
          alert("Your account is locked. Please contact fbpadmin@my-fbp.com for assistance.");
          location.replace("/signout.html");
          return;
        }
        if(userData.isPaidUser == false) {
          alert("Our records indicate that you have not paid your entry fee. Please submit your payment to participate in the pool.");
          location.replace("/makepayment.html");
          return;
        }
      } catch (error) {
        console.error("Error fetching user status:", error);
      }
    }