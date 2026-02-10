import heapq

graph = {
    "A": {"B": 4, "D": 2},
    "B": {"A": 4, "C": 3, "E": 2},
    "C": {"B": 3, "F": 3},
    "D": {"A": 2, "E": 3},
    "E": {"D": 3, "B": 2, "F": 2},
    "F": {"C": 3, "E": 2},
}


def dijkstra(graph, start):
    dist = {v: float("inf") for v in graph}
    prev = {v: None for v in graph}
    dist[start] = 0

    pq = [(0, start)]

    while pq:
        current_dist, u = heapq.heappop(pq)

        if current_dist > dist[u]:
            continue

        for v, w in graph[u].items():
            if dist[v] > current_dist + w:
                dist[v] = current_dist + w
                prev[v] = u
                heapq.heappush(pq, (dist[v], v))

    return dist, prev


def reconstruire_chemin(predecessors, start, end):
    chemin = []
    current = end
    while current is not None:
        chemin.append(current)
        if current == start:
            break
        current = predecessors[current]
    chemin.reverse()
    return chemin


if __name__ == "__main__":
    distances, predecessors = dijkstra(graph, "A")

    print("Distances minimales depuis A :")
    for node in sorted(distances):
        print(f"  d(A, {node}) = {distances[node]}")

    print("\nPredecesseurs :")
    for node in sorted(predecessors):
        print(f"  pred({node}) = {predecessors[node]}")

    chemin_AF = reconstruire_chemin(predecessors, "A", "F")
    print("\nPlus court chemin de A a F :")
    print(" -> ".join(chemin_AF))
    print("Longueur totale :", distances["F"])
