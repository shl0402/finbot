# Financial Knowledge Graph & Trading Signal Ontology

This ontology defines how news sentiment is dynamically translated into actionable trading signals. It determines market impact by evaluating two simultaneous dimensions: The Relationship Edge (Who are they to us?) and The Event Context (What kind of news is this?).

## 1. Horizontal Relationships (Peers, Competitors, Substitutes)

This layer handles entities that operate in the same market space or fight for the same capital allocation.

### 1.1. Zero-Sum Catalyst (Market Share Battle)

- **Definition**: The news involves an entity capturing a finite resource (a specific client contract, a patent, a direct product launch fighting your flagship product).
- **Logic**: Invert the sentiment.
- **Example**: Competitor wins a massive exclusive government contract (Positive for them) -> Negative Signal for Target.

### 1.2. Sector Tailwind / Headwind (Sympathy & Contagion)

- **Definition**: The news proves a macroeconomic or industry-wide trend. This usually triggers algorithmic ETF buying/selling that lifts or drags the whole sector.
- **Logic**: Match the sentiment.
- **Example**: Competitor crushes earnings specifically citing "massive unpredicted consumer demand across the industry" (Positive for them) -> Positive Signal for Target (Sympathy rally).

### 1.3. Capacity / Supply Destruction
- **Definition**: A peer suffers a structural failure, regulatory ban, or bankruptcy, removing their supply from the market.
- **Logic**: Invert the sentiment (Magnitude: High).
- **Example**: Competitor's primary factory burns down or they face a massive regulatory ban (Negative for them) -> Strong Positive Signal for Target (Market share up for grabs).

### 1.4. Substitution Threat

- **Definition**: News regarding an entity in an adjacent industry that produces a cheaper or more efficient alternative to your target's product.
- **Logic**: Invert the sentiment.
- **Example**: Solid-state battery tech achieves a major breakthrough (Positive for substitute) -> Negative Signal for Target (Traditional Lithium battery manufacturer).

## 2. Vertical Relationships (The Supply Chain)
This layer dictates how macroeconomic or firm-level shocks travel up and down the flow of revenue and raw materials.

### 2.1. Upstream: Supplier Tech Breakthrough / Capacity Expansion

- **Definition**: Your supplier invents a cheaper way to make a component, or builds a new factory ending a shortage.
- **Logic**: Match the sentiment.
- **Example**: TSMC perfects a cheaper 2nm chip process (Positive for Supplier) -> Positive Signal for Target (Apple, whose margins and product quality will improve).

### 2.2. Upstream: Supply Shock / Input Squeeze

- **Definition**: A supplier faces shortages, tariffs, or raw material cost spikes.
- **Logic**: Match the sentiment.
- **Example**: Major lithium miner slashes production guidance due to strikes (Negative for Supplier) -> Negative Signal for Target (EV manufacturer facing margin compression).

### 2.3. Downstream: Customer Demand Shock

- **Definition**: A major buyer of your target's product experiences a massive surge or drop in end-user sales.
- **Logic**: Match the sentiment.
- **Example**: Nvidia reports explosive GPU sales (Positive for Customer) -> Positive Signal for Target (SK Hynix, who supplies the memory chips for those GPUs).

### 2.4. Downstream: Customer Insolvency / Churn

- **Definition**: A major client loses funding, goes bankrupt, or switches to a different vendor.
- **Logic**: Match the sentiment.
- **Example**: A major telecom company cuts its CAPEX budget by 50% (Negative for Customer) -> Negative Signal for Target (Fiber-optic cable supplier).

## 3. Strategic & Ecosystem Relationships (The Network Effect)
This layer handles entities that are not direct competitors or traditional supply chain links, but whose success is fundamentally tied to the target.

### 3.1. Complementary Goods

- **Definition**: Products that are bought together. If demand for one rises, demand for the other rises.
- **Logic**: Match the sentiment.
- **Example**: US government passes massive subsidies for buying EVs (Positive for EVs) -> Positive Signal for Target (EV Charging Station networks).

### 3.2. Strategic Partners / Joint Ventures

- **Definition**: Entities your target has explicitly teamed up with for R&D, distribution, or marketing.
- **Logic**: Match the sentiment.
- **Example**: Partner company's new AI model goes viral (Positive for Partner) -> Positive Signal for Target (The company integrating that AI model).