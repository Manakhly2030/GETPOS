import React, { useState } from "react";
import "./index.css";
import NavigationItems from "./NavigationModules.json";
import ExportSvg from "./NavigationSvg";

const SideBar = () => {
  const [navigationItems, setNavigationItems] = useState(NavigationItems);

  const handleSideItem = (event, item_name) => {
    event.preventDefault();

    let sideItems = navigationItems;

    sideItems?.modules?.map((item) => {
      item.name === item_name ? (item.isActive = 1) : (item.isActive = 0);
    });

    setNavigationItems({ ...navigationItems, ...sideItems });
  };

  return (
    <div className="side-navbar">
      <ul className="side-navbar-items">
        <li className="navbar-item" style={{ marginTop: "1rem" }}>
          <a href="#">
            <img
              src="/assets/getpos/images/app_icon.ico"
              style={{ width: "6rem" }}
            />
          </a>
        </li>
        {navigationItems?.modules.length > 0 &&
          navigationItems?.modules.map((item) => {
            return (
              <li className="navbar-item navbar-item-card">
                <a href="" onClick={(e) => handleSideItem(e, item.name)}>
                  <div className={item.isActive ? "card card-active" : "card"}>
                    <div
                      className={
                        item.isActive
                          ? "item-image item-image-active"
                          : "item-image"
                      }
                    >
                      <ExportSvg item={item} />
                    </div>

                    <div
                      className={
                        item.isActive ? "content content-active" : "content"
                      }
                    >
                      <h4>{item.name}</h4>
                    </div>
                  </div>
                </a>
              </li>
            );
          })}
      </ul>
    </div>
  );
};

export default SideBar;
